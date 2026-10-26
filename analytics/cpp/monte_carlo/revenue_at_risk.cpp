// Monte Carlo revenue-at-risk simulator for ORBIT forecasts.
//
// Input CSV (header): region_id,horizon,forecast,log_sd
//   one row per region per forecast month. log_sd is the forecast uncertainty on the log scale.
// Model: log revenue_{r,h} = log forecast_{r,h} - sd^2/2 + sd * (sqrt(rho) * F_h + sqrt(1 - rho) * e_{r,h})
//   F_h is a common market factor shared across regions (cross-region correlation rho), e is idiosyncratic.
//   The -sd^2/2 term keeps the simulated mean equal to the point forecast.
// Output JSON: per region and total, expected revenue, P5/P50/P95, VaR95 (expected - P5) and CVaR95.
//
// Usage: revenue_at_risk --input fc.csv --output rar.json [--sims 200000] [--rho 0.35] [--seed 7]
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>

struct Row { std::string region; int horizon; double forecast; double log_sd; };

static std::string arg(int argc, char** argv, const std::string& name, const std::string& def) {
    for (int i = 1; i + 1 < argc; ++i) if (name == argv[i]) return argv[i + 1];
    return def;
}

static std::vector<Row> read_input(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open input: " + path);
    std::string line;
    std::getline(in, line);
    if (line.rfind("region_id,horizon,forecast,log_sd", 0) != 0) throw std::runtime_error("unexpected header: " + line);
    std::vector<Row> rows;
    int ln = 1;
    while (std::getline(in, line)) {
        ++ln;
        if (line.empty()) continue;
        std::stringstream ss(line);
        std::string a, b, c, d;
        if (!std::getline(ss, a, ',') || !std::getline(ss, b, ',') || !std::getline(ss, c, ',') || !std::getline(ss, d, ','))
            throw std::runtime_error("malformed line " + std::to_string(ln));
        Row r{a, std::stoi(b), std::stod(c), std::stod(d)};
        if (r.forecast <= 0 || r.log_sd < 0 || r.horizon < 1) throw std::runtime_error("invalid values on line " + std::to_string(ln));
        rows.push_back(r);
    }
    if (rows.empty()) throw std::runtime_error("no input rows");
    return rows;
}

struct Stats { double mean, p5, p50, p95, var95, cvar95; };

static Stats summarize(std::vector<double>& v) {
    double sum = 0;
    for (double x : v) sum += x;
    double mean = sum / v.size();
    std::sort(v.begin(), v.end());
    auto q = [&](double p) { return v[static_cast<size_t>(p * (v.size() - 1))]; };
    size_t tail = std::max<size_t>(1, static_cast<size_t>(0.05 * v.size()));
    double tail_sum = 0;
    for (size_t i = 0; i < tail; ++i) tail_sum += v[i];
    double p5 = q(0.05);
    return {mean, p5, q(0.5), q(0.95), mean - p5, mean - tail_sum / tail};
}

int main(int argc, char** argv) {
    try {
        const std::string input = arg(argc, argv, "--input", "");
        const std::string output = arg(argc, argv, "--output", "");
        if (input.empty() || output.empty()) {
            std::cerr << "usage: revenue_at_risk --input <csv> --output <json> [--sims N] [--rho R] [--seed S]\n";
            return 2;
        }
        const long sims = std::stol(arg(argc, argv, "--sims", "200000"));
        const double rho = std::stod(arg(argc, argv, "--rho", "0.35"));
        const uint64_t seed = std::stoull(arg(argc, argv, "--seed", "7"));
        if (sims < 1000 || rho < 0 || rho > 1) throw std::runtime_error("sims must be >= 1000 and rho in [0,1]");
        auto t0 = std::chrono::steady_clock::now();
        const auto rows = read_input(input);
        std::map<std::string, int> idx;
        int H = 0;
        for (const auto& r : rows) { if (!idx.count(r.region)) { int k = static_cast<int>(idx.size()); idx[r.region] = k; } H = std::max(H, r.horizon); }
        const int R = static_cast<int>(idx.size());
        std::mt19937_64 rng(seed);
        std::normal_distribution<double> N(0.0, 1.0);
        std::vector<std::vector<double>> region_tot(R, std::vector<double>(sims));
        std::vector<double> total(sims);
        std::vector<double> factor(H + 1);
        const double a = std::sqrt(rho), b = std::sqrt(1.0 - rho);
        double point_total = 0;
        for (const auto& r : rows) point_total += r.forecast;
        for (long s = 0; s < sims; ++s) {
            for (int h = 1; h <= H; ++h) factor[h] = N(rng);
            double t = 0;
            for (int k = 0; k < R; ++k) region_tot[k][s] = 0;
            for (const auto& r : rows) {
                const double z = a * factor[r.horizon] + b * N(rng);
                const double v = r.forecast * std::exp(r.log_sd * z - 0.5 * r.log_sd * r.log_sd);
                region_tot[idx[r.region]][s] += v;
                t += v;
            }
            total[s] = t;
        }
        std::ofstream out(output);
        if (!out) throw std::runtime_error("cannot open output: " + output);
        out << std::fixed << std::setprecision(2);
        auto emit = [&](const Stats& st) {
            out << "{\"expected\": " << st.mean << ", \"p5\": " << st.p5 << ", \"p50\": " << st.p50 << ", \"p95\": " << st.p95
                << ", \"var95\": " << st.var95 << ", \"cvar95\": " << st.cvar95 << "}";
        };
        out << "{\n  \"engine\": \"orbit-cpp-monte-carlo\", \"simulations\": " << sims << ", \"rho\": " << std::setprecision(4) << rho
            << ", \"seed\": " << seed << ", \"horizon_months\": " << H << ",\n" << std::setprecision(2)
            << "  \"point_forecast_total\": " << point_total << ",\n  \"regions\": {\n";
        int k = 0;
        for (const auto& [name, i] : idx) {
            Stats st = summarize(region_tot[i]);
            out << "    \"" << name << "\": ";
            emit(st);
            out << (++k < R ? ",\n" : "\n");
        }
        out << "  },\n  \"total\": ";
        Stats tot = summarize(total);
        emit(tot);
        const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        out << ",\n  \"elapsed_seconds\": " << std::setprecision(4) << secs << "\n}\n";
        std::cerr << "{\"simulations\": " << sims << ", \"regions\": " << R << ", \"elapsed_seconds\": " << secs << "}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << "\n";
        return 1;
    }
}
