//! CLI: orbit-anomaly-scorer --input ops.csv --output scores.csv [--window 28] [--min-periods 14]
//!
//! Input CSV header: series_key,operation_id,metric1,metric2,... rows sorted by series_key then date.
//! Output CSV: operation_id,<metric>_rz...,robust_score (max |z| with uptime sign-inverted handled upstream).
use orbit_anomaly_scorer::robust_z;
use std::collections::HashMap;
use std::fs;
use std::io::{BufWriter, Write};
use std::time::Instant;

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (input, output) = match (arg(&args, "--input"), arg(&args, "--output")) {
        (Some(i), Some(o)) => (i, o),
        _ => {
            eprintln!("usage: orbit-anomaly-scorer --input <csv> --output <csv> [--window N] [--min-periods N]");
            std::process::exit(2);
        }
    };
    let window: usize = arg(&args, "--window").map(|v| v.parse().expect("window")).unwrap_or(28);
    let min_p: usize = arg(&args, "--min-periods").map(|v| v.parse().expect("min-periods")).unwrap_or(14);
    let t0 = Instant::now();
    let text = fs::read_to_string(&input).unwrap_or_else(|e| {
        eprintln!("cannot read {input}: {e}");
        std::process::exit(1)
    });
    let mut lines = text.lines();
    let header: Vec<&str> = lines.next().expect("empty input").split(',').collect();
    if header.len() < 3 || header[0] != "series_key" || header[1] != "operation_id" {
        eprintln!("header must start with series_key,operation_id");
        std::process::exit(1);
    }
    let metrics: Vec<String> = header[2..].iter().map(|s| s.to_string()).collect();
    let mut order: Vec<String> = Vec::new();
    let mut series: HashMap<String, (Vec<String>, Vec<Vec<f64>>)> = HashMap::new();
    for (ln, line) in lines.enumerate() {
        let f: Vec<&str> = line.split(',').collect();
        if f.len() != header.len() {
            eprintln!("line {} has {} fields, expected {}", ln + 2, f.len(), header.len());
            std::process::exit(1);
        }
        let entry = series.entry(f[0].to_string()).or_insert_with(|| {
            order.push(f[0].to_string());
            (Vec::new(), vec![Vec::new(); metrics.len()])
        });
        entry.0.push(f[1].to_string());
        for (m, v) in f[2..].iter().enumerate() {
            entry.1[m].push(v.parse::<f64>().unwrap_or(f64::NAN));
        }
    }
    let out = fs::File::create(&output).expect("cannot create output");
    let mut w = BufWriter::new(out);
    let cols: Vec<String> = metrics.iter().map(|m| format!("{m}_rz")).collect();
    writeln!(w, "operation_id,{},robust_score", cols.join(",")).unwrap();
    let mut rows = 0usize;
    for key in &order {
        let (ids, vals) = &series[key];
        let zs: Vec<Vec<f64>> = vals.iter().map(|v| robust_z(v, window, min_p)).collect();
        for i in 0..ids.len() {
            let mut best = 0.0f64;
            let mut parts = Vec::with_capacity(zs.len());
            for z in &zs {
                let v = z[i];
                if v.is_finite() && v.abs() > best {
                    best = v.abs();
                }
                parts.push(if v.is_finite() { format!("{v:.6}") } else { String::new() });
            }
            writeln!(w, "{},{},{best:.6}", ids[i], parts.join(",")).unwrap();
            rows += 1;
        }
    }
    w.flush().unwrap();
    eprintln!(
        "{{\"rows\": {rows}, \"series\": {}, \"metrics\": {}, \"window\": {window}, \"elapsed_ms\": {:.3}}}",
        order.len(),
        metrics.len(),
        t0.elapsed().as_secs_f64() * 1000.0
    );
}
