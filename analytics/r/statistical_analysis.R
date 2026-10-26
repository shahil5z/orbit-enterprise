#!/usr/bin/env Rscript
# ORBIT statistical workflow (base R stats + jsonlite).
# Why R: hypothesis tests, Tukey HSD, regression diagnostics and STL decomposition are first-class,
# well-validated in base R, so this workflow needs no extra statistical packages.
#
# Input : outputs/analytics/region_monthly.csv (written by the ANALYZE stage from the Spark mart)
# Output: outputs/r/statistics.json (consumed by the decision engine and served by the API)
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: statistical_analysis.R <region_monthly.csv> <output.json>")
df <- read.csv(args[1], stringsAsFactors = FALSE)
required <- c("region_id", "month", "revenue", "cost", "opex", "headcount", "incident_count",
              "fx_volatility", "compliance_score", "avg_uptime_pct")
missing <- setdiff(required, names(df))
if (length(missing) > 0) stop(paste("missing columns:", paste(missing, collapse = ", ")))
df$month <- as.Date(df$month)
df$year <- as.integer(format(df$month, "%Y"))
df$moy <- as.integer(format(df$month, "%m"))
df$operating_margin <- (df$revenue - df$cost - df$opex) / df$revenue
set.seed(20260101)

ci_list <- function(ci) list(lower = unname(ci[1]), upper = unname(ci[2]), level = attr(ci, "conf.level"))

# 1. Paired t-test per region: 2025 monthly revenue vs the same month in 2024
yoy <- lapply(split(df, df$region_id), function(g) {
  a <- g[g$year == 2025, c("moy", "revenue")]
  b <- g[g$year == 2024, c("moy", "revenue")]
  m <- merge(a, b, by = "moy", suffixes = c("_2025", "_2024"))
  growth <- m$revenue_2025 / m$revenue_2024 - 1
  tt <- t.test(log(m$revenue_2025), log(m$revenue_2024), paired = TRUE)
  list(region_id = g$region_id[1], months = nrow(m), mean_yoy_growth = mean(growth),
       log_diff_estimate = unname(tt$estimate), t = unname(tt$statistic), df = unname(tt$parameter),
       p_value = tt$p.value, ci_growth = list(lower = exp(tt$conf.int[1]) - 1, upper = exp(tt$conf.int[2]) - 1,
       level = 0.95), significant_at_0_05 = tt$p.value < 0.05,
       direction = ifelse(tt$p.value < 0.05, ifelse(tt$estimate > 0, "growth", "decline"), "no significant change"))
})

# 2. One-way ANOVA + Tukey HSD: does operating margin differ by region?
aov_fit <- aov(operating_margin ~ factor(region_id), data = df)
aov_sum <- summary(aov_fit)[[1]]
tk <- TukeyHSD(aov_fit)[[1]]
tukey <- lapply(seq_len(nrow(tk)), function(i) list(pair = rownames(tk)[i], diff = tk[i, "diff"],
  lower = tk[i, "lwr"], upper = tk[i, "upr"], p_adj = tk[i, "p adj"]))
margin_by_region <- aggregate(operating_margin ~ region_id, data = df, FUN = mean)

# 3. Regression: drivers of log revenue with region and month-of-year fixed effects
fit <- lm(log(revenue) ~ log(headcount) + incident_count + fx_volatility + compliance_score + avg_uptime_pct +
            factor(region_id) + factor(moy), data = df)
co <- summary(fit)$coefficients
ci <- confint(fit)
keep <- !grepl("^factor", rownames(co))
coefs <- lapply(which(keep), function(i) list(term = rownames(co)[i], estimate = co[i, 1], std_error = co[i, 2],
  t = co[i, 3], p_value = co[i, 4], ci_lower = ci[i, 1], ci_upper = ci[i, 2]))
sw <- shapiro.test(residuals(fit))

# 4. STL decomposition of total monthly revenue
tot <- aggregate(revenue ~ month, data = df, FUN = sum)
tot <- tot[order(tot$month), ]
y <- ts(tot$revenue, frequency = 12, start = c(as.integer(format(min(tot$month), "%Y")), 1))
dec <- stl(log(y), s.window = "periodic", robust = TRUE)
comp <- dec$time.series
seasonal_strength <- max(0, 1 - var(comp[, "remainder"]) / var(comp[, "seasonal"] + comp[, "remainder"]))
trend_strength <- max(0, 1 - var(comp[, "remainder"]) / var(comp[, "trend"] + comp[, "remainder"]))
seasonal_index <- tapply(exp(comp[, "seasonal"]), cycle(y), mean)

# 5. Correlation test: incidents vs uptime
ct <- cor.test(df$incident_count, df$avg_uptime_pct, method = "spearman", exact = FALSE)

out <- list(
  engine = paste("R", R.version$major, R.version$minor, sep = "."), generated_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  observations = nrow(df),
  yoy_paired_tests = unname(yoy),
  operating_margin_anova = list(F = aov_sum[1, "F value"], df_between = aov_sum[1, "Df"], df_within = aov_sum[2, "Df"],
    p_value = aov_sum[1, "Pr(>F)"], region_means = setNames(as.list(margin_by_region$operating_margin), margin_by_region$region_id),
    tukey_hsd = tukey),
  revenue_regression = list(formula = deparse(formula(fit)), r_squared = summary(fit)$r.squared,
    adj_r_squared = summary(fit)$adj.r.squared, n = nobs(fit), coefficients = unname(coefs),
    residual_shapiro_p = sw$p.value, note = "region and month-of-year fixed effects omitted from coefficient list"),
  stl_decomposition = list(series = "log total monthly revenue", seasonal_strength = seasonal_strength,
    trend_strength = trend_strength, seasonal_index_by_month = as.list(unname(seasonal_index)),
    trend_start = exp(comp[1, "trend"]), trend_end = exp(comp[nrow(comp), "trend"])),
  incident_uptime_correlation = list(method = "spearman", rho = unname(ct$estimate), p_value = ct$p.value)
)
dir.create(dirname(args[2]), showWarnings = FALSE, recursive = TRUE)
write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE, na = "null"), args[2])
cat("R_STATS_OK", args[2], "\n")
