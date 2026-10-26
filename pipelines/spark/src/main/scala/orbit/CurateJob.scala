package orbit

import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.expressions.Window
import org.apache.spark.sql.functions._

/**
 * CURATE stage. Input: conformed Parquet (data/curated/conformed). Output: analytical marts
 * (data/curated/marts) used by analytics, ML, risk and the database seed.
 *
 *  - monthly_kpis          region x business unit x month KPIs with lag/rolling/YoY/YTD window features
 *  - region_monthly        region x month revenue, cost, opex and risk indicators (forecast + R input)
 *  - customer_features     RFM, trend and diversity features observed up to the cutoff, plus churn label
 *  - ops_daily_features    trailing 28 day rolling mean/std and z-scores for operational anomaly detection
 *  - segment_profile       segment x region aggregates for segmentation prep
 *
 * Usage: CurateJob <conformedDir> <martsDir> [cutoffDate=2025-09-30]
 */
object CurateJob {
  def main(args: Array[String]): Unit = {
    require(args.length >= 2, "usage: CurateJob <conformedDir> <martsDir> [cutoffDate]")
    val in = args(0)
    val out = args(1)
    val cutoff = if (args.length > 2) args(2) else "2025-09-30"
    val spark = SparkSession.builder()
      .appName("orbit-curate")
      .master(sys.env.getOrElse("ORBIT_SPARK_MASTER", "local[*]"))
      .config("spark.sql.shuffle.partitions", "8")
      .config("spark.sql.session.timeZone", "UTC")
      .config("spark.ui.enabled", "false")
      .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    val t0 = System.nanoTime()

    def read(name: String): DataFrame = spark.read.parquet(s"$in/$name.parquet")
    val tx = read("transactions")
    val ops = read("operations")
    val inc = read("incidents")
    val cust = read("customers")
    val risk = read("risk_indicators")

    // ---------- monthly KPIs (multi-dataset join + windows) ----------
    val txM = tx.groupBy(col("region_id"), col("bu_id"), date_trunc("month", col("txn_date")).cast("date").as("month"))
      .agg(sum("revenue").as("revenue"), sum("cost").as("cost"), sum("gross_margin").as("gross_margin"),
        count(lit(1)).as("txn_count"), countDistinct("customer_id").as("active_customers"),
        avg("discount_pct").as("avg_discount"))
    val opsM = ops.groupBy(col("region_id"), col("bu_id"), date_trunc("month", col("op_date")).cast("date").as("month"))
      .agg(sum("opex").as("opex"), sum("marketing_spend").as("marketing_spend"), avg("headcount").as("avg_headcount"),
        avg("uptime_pct").as("avg_uptime_pct"), avg("fulfillment_hours").as("avg_fulfillment_hours"),
        sum("support_tickets").as("support_tickets"))
    val incM = inc.groupBy(col("region_id"), col("bu_id"), date_trunc("month", col("opened_at")).cast("date").as("month"))
      .agg(count(lit(1)).as("incident_count"), sum("cost_impact").as("incident_cost"),
        sum(when(col("severity").isin("SEV1", "SEV2"), 1).otherwise(0)).as("major_incidents"))
    val w = Window.partitionBy("region_id", "bu_id").orderBy("month")
    val kpis = txM.join(opsM, Seq("region_id", "bu_id", "month"), "full_outer")
      .join(incM, Seq("region_id", "bu_id", "month"), "left")
      .na.fill(0, Seq("revenue", "cost", "gross_margin", "txn_count", "active_customers", "incident_count",
        "incident_cost", "major_incidents"))
      .withColumn("operating_profit", col("gross_margin") - col("opex"))
      .withColumn("gross_margin_pct", when(col("revenue") > 0, col("gross_margin") / col("revenue")))
      .withColumn("avg_order_value", when(col("txn_count") > 0, col("revenue") / col("txn_count")))
      .withColumn("revenue_per_head", when(col("avg_headcount") > 0, col("revenue") / col("avg_headcount")))
      .withColumn("revenue_lag1", lag("revenue", 1).over(w))
      .withColumn("revenue_mom_growth", when(col("revenue_lag1") > 0, col("revenue") / col("revenue_lag1") - 1))
      .withColumn("revenue_yoy_growth", when(lag("revenue", 12).over(w) > 0, col("revenue") / lag("revenue", 12).over(w) - 1))
      .withColumn("revenue_roll3", avg("revenue").over(w.rowsBetween(-2, 0)))
      .withColumn("revenue_ytd", sum("revenue").over(Window.partitionBy(col("region_id"), col("bu_id"), year(col("month")))
        .orderBy("month").rowsBetween(Window.unboundedPreceding, 0)))
      .withColumn("region_rank_in_month", dense_rank().over(Window.partitionBy("bu_id", "month").orderBy(desc("revenue"))))
      .orderBy("region_id", "bu_id", "month")
    kpis.write.mode("overwrite").parquet(s"$out/monthly_kpis")

    // ---------- region x month (forecast + statistics input) ----------
    val wr = Window.partitionBy("region_id").orderBy("month")
    val regionMonthly = kpis.groupBy("region_id", "month")
      .agg(sum("revenue").as("revenue"), sum("cost").as("cost"), sum("opex").as("opex"),
        sum("marketing_spend").as("marketing_spend"), sum("avg_headcount").as("headcount"),
        sum("txn_count").as("txn_count"), sum("incident_count").as("incident_count"),
        sum("incident_cost").as("incident_cost"), avg("avg_uptime_pct").as("avg_uptime_pct"))
      .join(risk.select(col("region_id"), col("month").cast("date").as("month"), col("fx_volatility"),
        col("compliance_score"), col("supplier_concentration"), col("credit_exposure")), Seq("region_id", "month"), "left")
      .withColumn("revenue_lag1", lag("revenue", 1).over(wr))
      .withColumn("revenue_lag12", lag("revenue", 12).over(wr))
      .withColumn("revenue_roll3", avg("revenue").over(wr.rowsBetween(-2, 0)))
      .withColumn("month_of_year", month(col("month")))
      .orderBy("region_id", "month")
    regionMonthly.write.mode("overwrite").parquet(s"$out/region_monthly")

    // ---------- customer features with churn label ----------
    val cut = to_date(lit(cutoff))
    val hist = tx.filter(col("txn_date") <= cut)
    val future = tx.filter(col("txn_date") > cut && col("txn_date") <= date_add(cut, 90))
      .groupBy("customer_id").agg(count(lit(1)).as("future_txns"))
    val feats = hist.groupBy("customer_id").agg(
      max("txn_date").as("last_txn_date"), min("txn_date").as("first_txn_date"), count(lit(1)).as("frequency"),
      sum("revenue").as("monetary"), avg("revenue").as("avg_txn_value"), avg("discount_pct").as("avg_discount"),
      countDistinct("product_id").as("distinct_products"), countDistinct("bu_id").as("distinct_bus"),
      sum(when(col("txn_date") > date_sub(cut, 90), col("revenue")).otherwise(0)).as("revenue_last_90d"),
      sum(when(col("txn_date") > date_sub(cut, 180) && col("txn_date") <= date_sub(cut, 90), col("revenue")).otherwise(0)).as("revenue_prev_90d"),
      sum(when(col("txn_date") > date_sub(cut, 90), 1).otherwise(0)).as("txns_last_90d"),
      avg(when(col("channel") === "online", 1).otherwise(0)).as("online_share"))
    val customerFeatures = cust.select("customer_id", "region_id", "segment", "industry", "satisfaction_score", "credit_limit")
      .join(feats, Seq("customer_id"), "inner")
      .join(future, Seq("customer_id"), "left")
      .withColumn("recency_days", datediff(cut, col("last_txn_date")))
      .withColumn("tenure_days", datediff(cut, col("first_txn_date")))
      .withColumn("revenue_trend", (col("revenue_last_90d") + 1) / (col("revenue_prev_90d") + 1))
      // label: a customer active in the last 180 days of history that makes no purchase in the next 90 days
      .filter(col("last_txn_date") > date_sub(cut, 180))
      .withColumn("churned_next_90d", when(coalesce(col("future_txns"), lit(0)) === 0, 1).otherwise(0))
      .drop("future_txns")
      .withColumn("cutoff_date", cut)
    customerFeatures.write.mode("overwrite").parquet(s"$out/customer_features")

    // ---------- operational daily anomaly features ----------
    val wo = Window.partitionBy("region_id", "bu_id").orderBy("op_date").rowsBetween(-28, -1)
    var opsF = ops.select("operation_id", "op_date", "region_id", "bu_id", "opex", "fulfillment_hours", "uptime_pct",
      "support_tickets", "orders_processed", "headcount")
    for (c <- Seq("opex", "fulfillment_hours", "uptime_pct", "support_tickets")) {
      opsF = opsF.withColumn(s"${c}_mean28", avg(c).over(wo))
        .withColumn(s"${c}_std28", stddev(c).over(wo))
        .withColumn(s"${c}_z", (col(c) - col(s"${c}_mean28")) / when(col(s"${c}_std28") > 0, col(s"${c}_std28")))
    }
    opsF.orderBy("region_id", "bu_id", "op_date").write.mode("overwrite").parquet(s"$out/ops_daily_features")

    // ---------- segmentation prep ----------
    val segProfile = customerFeatures.groupBy("segment", "region_id")
      .agg(count(lit(1)).as("customers"), avg("monetary").as("avg_monetary"), avg("frequency").as("avg_frequency"),
        avg("recency_days").as("avg_recency_days"), avg("churned_next_90d").as("churn_rate"))
    segProfile.write.mode("overwrite").parquet(s"$out/segment_profile")

    val secs = (System.nanoTime() - t0) / 1e9
    val counts = Seq("monthly_kpis" -> kpis.count(), "region_monthly" -> regionMonthly.count(),
      "customer_features" -> customerFeatures.count(), "ops_daily_features" -> opsF.count(),
      "segment_profile" -> segProfile.count())
    val json = counts.map { case (k, v) => s""""$k": $v""" }.mkString("{", ", ", s""", "spark_version": "${spark.version}", "seconds": $secs}""")
    println("CURATE_RESULT " + json)
    spark.stop()
  }
}
