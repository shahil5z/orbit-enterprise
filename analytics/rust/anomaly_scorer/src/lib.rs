//! Robust trailing-window anomaly scoring.
//!
//! For each series and metric the score at time t is |x_t - median(W)| / (1.4826 * MAD(W)) where W is
//! the previous `window` observations (the current point is excluded so it cannot mask itself).

pub const MAD_SCALE: f64 = 1.4826;

fn median_in_place(v: &mut [f64]) -> f64 {
    let n = v.len();
    let mid = n / 2;
    let (_, m, _) = v.select_nth_unstable_by(mid, |a, b| a.partial_cmp(b).unwrap());
    let upper = *m;
    if n % 2 == 1 {
        upper
    } else {
        let lower = v[..mid].iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        (lower + upper) / 2.0
    }
}

/// Robust z-scores for one series. Returns NaN until `min_periods` history points exist.
pub fn robust_z(series: &[f64], window: usize, min_periods: usize) -> Vec<f64> {
    let mut out = vec![f64::NAN; series.len()];
    let mut buf: Vec<f64> = Vec::with_capacity(window);
    let mut dev: Vec<f64> = Vec::with_capacity(window);
    for t in 0..series.len() {
        let start = t.saturating_sub(window);
        buf.clear();
        buf.extend(series[start..t].iter().cloned().filter(|x| x.is_finite()));
        if buf.len() < min_periods || !series[t].is_finite() {
            continue;
        }
        let med = median_in_place(&mut buf);
        dev.clear();
        dev.extend(buf.iter().map(|x| (x - med).abs()));
        let mad = median_in_place(&mut dev);
        out[t] = if mad > 0.0 { (series[t] - med) / (MAD_SCALE * mad) } else { 0.0 };
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn median_odd_even() {
        assert_eq!(median_in_place(&mut [3.0, 1.0, 2.0]), 2.0);
        assert_eq!(median_in_place(&mut [4.0, 1.0, 3.0, 2.0]), 2.5);
    }

    #[test]
    fn spike_scores_high_and_flat_scores_zero() {
        let mut s: Vec<f64> = (0..40).map(|i| 10.0 + (i % 3) as f64).collect();
        s[35] = 100.0;
        let z = robust_z(&s, 28, 10);
        assert!(z[5].is_nan());
        assert!(z[35] > 20.0);
        assert!(z[30].abs() < 2.0);
        let flat = robust_z(&[5.0; 20], 10, 5);
        assert_eq!(flat[15], 0.0);
    }
}
