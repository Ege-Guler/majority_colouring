/**
 * scrape_colorable.cpp
 * ====================
 * Stream-filter a majority-colouring results CSV by chromatic number and write
 * a smaller CSV.  Designed to handle the 38 GB 6-vertex file (1.07 billion
 * rows) without loading it into RAM.  Uses a 64 MB read buffer for near-disk-
 * speed throughput.
 *
 * ----------------------------------------------------------------------------
 * BUILD
 * ----------------------------------------------------------------------------
 *   cd tools
 *   make              # optimised release build  → ./scrape_colorable
 *   make debug        # debug build with sanitisers
 *   make clean
 *
 * Requirements: g++ (or clang++) with C++17 support.
 *
 * ----------------------------------------------------------------------------
 * USAGE
 * ----------------------------------------------------------------------------
 *   ./scrape_colorable [options]
 *
 * Options:
 *   --input  <path>         Input CSV (default: ../notebooks/results_6vertex.csv)
 *   --output <path>         Output CSV (default: auto-named, see below)
 *   --chromatic <n>         Chromatic number to keep (default: 3; ignored by
 *                           --edge-stats unless explicitly set)
 *   --max <n>               Keep only the first N matching rows; stop early.
 *   --random <n>            Reservoir-sample exactly N matching rows uniformly
 *                           at random (Vitter Algorithm R). Scans entire file.
 *                           Output rows are written in original file order.
 *   --seed <n>              RNG seed for --random / --stratified-edges
 *                           (default: random_device, non-reproducible)
 *   --stratified-edges <n>  Sample N graphs distributed evenly across distinct
 *                           edge-count values.  Does two passes: first counts
 *                           per-bucket totals, then reservoir-samples each
 *                           bucket independently.  Output is in file order.
 *   --edge-stats            Print edge-count statistics (global max and the
 *                           top-20% threshold) then exit. No CSV is written.
 *                           Combines with --chromatic to restrict the analysis;
 *                           without --chromatic all rows are counted.
 *   --no-progress           Suppress progress messages on stderr
 *   -h / --help             Print this help and exit
 *
 * --max, --random, --stratified-edges, and --edge-stats are mutually exclusive.
 *
 * ----------------------------------------------------------------------------
 * AUTO-NAMED OUTPUT FILES
 * ----------------------------------------------------------------------------
 *   --max 1000                      → results_6vertex_chromatic3_first1000.csv
 *   --random 1000                   → results_6vertex_chromatic3_random1000.csv
 *   --stratified-edges 100000       → results_6vertex_chromatic3_stratified100000.csv
 *   (neither flag)                  → results_6vertex_chromatic3.csv
 *   --chromatic 2 --random 500      → results_6vertex_chromatic2_random500.csv
 *
 * ----------------------------------------------------------------------------
 * EXAMPLES
 * ----------------------------------------------------------------------------
 *   # First 1000 chromatic-3 graphs (fast — stops early)
 *   ./scrape_colorable --max 1000
 *
 *   # Random 1000 chromatic-3 graphs (scans full 38 GB)
 *   ./scrape_colorable --random 1000
 *
 *   # 100 000 graphs spread evenly across edge counts (chromatic-3)
 *   ./scrape_colorable --stratified-edges 100000
 *
 *   # Same but across all chromatic classes
 *   ./scrape_colorable --stratified-edges 100000 --chromatic 0
 *
 *   # Edge statistics across ALL graphs
 *   ./scrape_colorable --edge-stats
 *
 *   # Edge statistics for chromatic-3 graphs only
 *   ./scrape_colorable --edge-stats --chromatic 3
 *
 * ----------------------------------------------------------------------------
 * PERFORMANCE NOTES
 * ----------------------------------------------------------------------------
 *   --max              : exits as soon as N rows are collected.
 *   --random           : single pass, ~75-80 s for the 38 GB file.
 *   --stratified-edges : two full passes (~150-160 s for 38 GB).  Per-bucket
 *                        reservoirs are kept in RAM; total memory is O(N) rows.
 *   --edge-stats       : single pass, O(max_edges) memory.
 *
 * ----------------------------------------------------------------------------
 * CSV FORMAT (input & output)
 * ----------------------------------------------------------------------------
 *   mask, num_edges, chromatic_number, is_isomorphic, is_cyclic,
 *   connectivity_number, stability_number, clique_number, has_hamiltonian_path
 */

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

// --------------------------------------------------------------------------
// I/O buffer size: 64 MB gives near-sequential-disk throughput
// --------------------------------------------------------------------------
static constexpr std::size_t IO_BUF = 64ULL * 1024 * 1024;

// --------------------------------------------------------------------------
// Parse the chromatic_number column (0-indexed column 2) from a CSV line.
// Returns -1 if the line is malformed.
// --------------------------------------------------------------------------
static int parse_chromatic(const char* line)
{
    int commas = 0;
    const char* p = line;
    while (*p && commas < 2) {
        if (*p++ == ',') ++commas;
    }
    if (commas < 2 || *p == '\0') return -1;
    char* end;
    long v = std::strtol(p, &end, 10);
    if (end == p) return -1;
    return static_cast<int>(v);
}

// --------------------------------------------------------------------------
// Parse the num_edges column (0-indexed column 1) from a CSV line.
// Returns -1 if the line is malformed.
// --------------------------------------------------------------------------
static int parse_num_edges(const char* line)
{
    const char* p = line;
    while (*p && *p != ',') ++p;  // skip column 0 (mask)
    if (*p == '\0') return -1;
    ++p;  // skip comma
    char* end;
    long v = std::strtol(p, &end, 10);
    if (end == p) return -1;
    return static_cast<int>(v);
}

// --------------------------------------------------------------------------
// Config
// --------------------------------------------------------------------------
struct Config {
    std::string input_path    = "../notebooks/results_6vertex.csv";
    std::string output_path;
    int         chromatic     = -1;      // -1 = not set; defaulted below
    bool        chromatic_set = false;
    long long   max_count     = -1;
    long long   random_n      = -1;
    long long   stratified_n  = -1;
    bool        edge_stats    = false;
    uint64_t    seed          = 0;
    bool        auto_seed     = true;
    bool        progress      = true;
};

static void usage(const char* argv0)
{
    std::cerr
        << "Usage: " << argv0 << " [options]\n"
        << "\n"
        << "  --input  <path>         Input CSV (default: ../notebooks/results_6vertex.csv)\n"
        << "  --output <path>         Output CSV (default: auto-named)\n"
        << "  --chromatic <n>         Target chromatic number (default: 3 for filter modes;\n"
        << "                          no filter for --edge-stats unless this flag is given)\n"
        << "  --max <n>               Take first N matching rows\n"
        << "  --random <n>            Reservoir-sample N matching rows (uniform)\n"
        << "  --stratified-edges <n>  Sample N rows evenly across edge-count buckets\n"
        << "  --seed <n>              RNG seed (default: random_device)\n"
        << "  --edge-stats            Print edge-count stats, no CSV written\n"
        << "  --no-progress           Suppress progress to stderr\n"
        << "\n"
        << "Examples:\n"
        << "  ./scrape_colorable --max 1000\n"
        << "  ./scrape_colorable --random 1000\n"
        << "  ./scrape_colorable --stratified-edges 100000\n"
        << "  ./scrape_colorable --edge-stats\n"
        << "  ./scrape_colorable --edge-stats --chromatic 3\n";
}

static Config parse_args(int argc, char** argv)
{
    Config cfg;
    for (int i = 1; i < argc; ++i) {
        auto require_next = [&](const char* flag) -> const char* {
            if (i + 1 >= argc) {
                std::cerr << "error: " << flag << " requires an argument\n";
                std::exit(1);
            }
            return argv[++i];
        };

        if (!std::strcmp(argv[i], "--input")) {
            cfg.input_path = require_next("--input");
        } else if (!std::strcmp(argv[i], "--output")) {
            cfg.output_path = require_next("--output");
        } else if (!std::strcmp(argv[i], "--chromatic")) {
            cfg.chromatic     = std::atoi(require_next("--chromatic"));
            cfg.chromatic_set = true;
        } else if (!std::strcmp(argv[i], "--max")) {
            cfg.max_count = std::atoll(require_next("--max"));
        } else if (!std::strcmp(argv[i], "--random")) {
            cfg.random_n = std::atoll(require_next("--random"));
        } else if (!std::strcmp(argv[i], "--stratified-edges")) {
            cfg.stratified_n = std::atoll(require_next("--stratified-edges"));
        } else if (!std::strcmp(argv[i], "--seed")) {
            cfg.seed      = std::stoull(require_next("--seed"));
            cfg.auto_seed = false;
        } else if (!std::strcmp(argv[i], "--edge-stats")) {
            cfg.edge_stats = true;
        } else if (!std::strcmp(argv[i], "--no-progress")) {
            cfg.progress = false;
        } else if (!std::strcmp(argv[i], "--help") || !std::strcmp(argv[i], "-h")) {
            usage(argv[0]);
            std::exit(0);
        } else {
            std::cerr << "error: unknown argument: " << argv[i] << "\n";
            usage(argv[0]);
            std::exit(1);
        }
    }

    int mode_count = (cfg.max_count != -1) + (cfg.random_n != -1)
                   + (cfg.stratified_n != -1) + cfg.edge_stats;
    if (mode_count > 1) {
        std::cerr << "error: --max, --random, --stratified-edges, and --edge-stats "
                     "are mutually exclusive\n";
        std::exit(1);
    }

    // For filter/output modes, default chromatic to 3 if not explicitly set.
    // For --edge-stats without --chromatic, -1 means "all chromatic classes".
    if (!cfg.chromatic_set && !cfg.edge_stats)
        cfg.chromatic = 3;

    if (cfg.output_path.empty() && !cfg.edge_stats) {
        std::string base = cfg.input_path;
        auto slash = base.rfind('/');
        if (slash != std::string::npos) base = base.substr(slash + 1);
        auto dot = base.rfind('.');
        if (dot != std::string::npos) base = base.substr(0, dot);

        base += "_chromatic" + std::to_string(cfg.chromatic);
        if (cfg.max_count != -1)
            base += "_first"       + std::to_string(cfg.max_count);
        else if (cfg.random_n != -1)
            base += "_random"      + std::to_string(cfg.random_n);
        else if (cfg.stratified_n != -1)
            base += "_stratified"  + std::to_string(cfg.stratified_n);
        base += ".csv";
        cfg.output_path = base;
    }

    return cfg;
}

// --------------------------------------------------------------------------
// Edge-statistics mode.
// Prints global max num_edges and the top-20% threshold (largest x such
// that at least 20% of matching rows have num_edges > x).
// --------------------------------------------------------------------------
static void run_edge_stats(
    std::ifstream& in,
    int target_chromatic,   // -1 = no filter
    bool progress)
{
    std::vector<long long> hist;

    std::string line;
    long long total_lines = 0;
    long long matched     = 0;

    constexpr long long REPORT_EVERY = 50'000'000LL;

    while (std::getline(in, line)) {
        ++total_lines;
        if (progress && total_lines % REPORT_EVERY == 0)
            std::cerr << "  scanned " << total_lines / 1'000'000 << "M rows, "
                      << "matched " << matched << " ...\n";

        if (target_chromatic != -1 &&
            parse_chromatic(line.c_str()) != target_chromatic)
            continue;

        int e = parse_num_edges(line.c_str());
        if (e < 0) continue;

        auto idx = static_cast<std::size_t>(e);
        if (idx >= hist.size()) hist.resize(idx + 1, 0LL);
        ++hist[idx];
        ++matched;
    }

    if (matched == 0) {
        std::cout << "No matching rows found.\n";
        return;
    }

    int max_edges = static_cast<int>(hist.size()) - 1;

    // Largest x where count(num_edges > x) >= 20% of matched.
    long long threshold = matched / 5;
    long long above     = 0;
    int       top20_threshold = -1;
    for (int e = max_edges; e >= 0; --e) {
        if (above >= threshold) {
            top20_threshold = e;
            break;
        }
        above += hist[static_cast<std::size_t>(e)];
    }

    long long above_threshold = (top20_threshold >= 0) ? above : 0;
    long long pct_above = above_threshold * 100 / matched;

    std::cout << "Matched graphs         : " << matched           << "\n"
              << "Global max num_edges   : " << max_edges         << "\n"
              << "Top-20% threshold      : " << top20_threshold   << "\n"
              << "  => " << above_threshold << " graphs ("
              << pct_above << "%) have num_edges > " << top20_threshold << "\n";
}

// --------------------------------------------------------------------------
// Stratified-edges mode.
// Two passes:
//   1. Count matching rows per edge-count bucket.
//   2. Reservoir-sample each bucket independently with per-bucket quota.
//
// Quota allocation: base = floor(n / B), first (n % B) buckets get base+1.
// If a bucket has fewer rows than its quota, all rows are taken.
// Output rows are written in the original file order.
// --------------------------------------------------------------------------
static void run_stratified_edges(
    const std::string& input_path,
    std::ofstream&     out,
    const std::string& header,
    int                target_chromatic,
    long long          total_n,
    uint64_t           seed,
    bool               progress)
{
    constexpr long long REPORT_EVERY = 50'000'000LL;

    // ---- Pass 1: histogram ------------------------------------------------
    if (progress) std::cerr << "Pass 1: counting per-bucket rows...\n";

    std::vector<long long> hist;
    {
        std::ifstream in(input_path, std::ios::binary);
        static char buf1[IO_BUF];
        in.rdbuf()->pubsetbuf(buf1, sizeof(buf1));
        std::string skip; std::getline(in, skip);  // skip header

        std::string line;
        long long total_lines = 0;
        while (std::getline(in, line)) {
            ++total_lines;
            if (progress && total_lines % REPORT_EVERY == 0)
                std::cerr << "  pass1: " << total_lines / 1'000'000 << "M rows\n";
            if (target_chromatic != -1 &&
                parse_chromatic(line.c_str()) != target_chromatic)
                continue;
            int e = parse_num_edges(line.c_str());
            if (e < 0) continue;
            auto idx = static_cast<std::size_t>(e);
            if (idx >= hist.size()) hist.resize(idx + 1, 0LL);
            ++hist[idx];
        }
    }

    if (hist.empty()) {
        std::cerr << "No matching rows found.\n";
        return;
    }

    // Build list of non-empty buckets and allocate per-bucket quotas
    struct Bucket { int edge_val; long long count; long long quota; };
    std::vector<Bucket> buckets;
    for (std::size_t i = 0; i < hist.size(); ++i) {
        if (hist[i] > 0)
            buckets.push_back({static_cast<int>(i), hist[i], 0});
    }

    long long B = static_cast<long long>(buckets.size());

    // Reserve 1 slot for the max-edge bucket so it is always present,
    // then distribute the remaining (total_n - 1) slots evenly.
    long long last   = B - 1;
    long long budget = std::max(0LL, total_n - 1);  // slots for buckets 0..last-1
    long long base_q = (B > 1) ? budget / (B - 1) : 0;
    long long extra  = (B > 1) ? budget % (B - 1) : 0;  // first `extra` non-max buckets get +1

    long long total_sampled = 0;
    for (long long b = 0; b < B; ++b) {
        long long q;
        if (b == last) {
            q = 1;  // guaranteed slot for max-edge bucket
        } else {
            q = base_q + (b < extra ? 1 : 0);
        }
        buckets[static_cast<std::size_t>(b)].quota =
            std::min(q, buckets[static_cast<std::size_t>(b)].count);
        total_sampled += buckets[static_cast<std::size_t>(b)].quota;
    }

    if (progress) {
        std::cerr << "  " << B << " non-empty edge-count buckets\n";
        std::cerr << "  target " << total_n << ", will sample " << total_sampled << "\n";
        std::cerr << "Pass 2: reservoir-sampling each bucket...\n";
    }

    // ---- Pass 2: per-bucket reservoir sampling ----------------------------
    // reservoirs[i] stores {file_row_index, line} for bucket i
    struct Slot { long long idx; std::string line; };
    std::vector<std::vector<Slot>> reservoirs(static_cast<std::size_t>(B));
    for (std::size_t b = 0; b < static_cast<std::size_t>(B); ++b)
        reservoirs[b].reserve(static_cast<std::size_t>(buckets[b].quota));

    // Map edge value → bucket index for O(1) lookup
    int max_edge = buckets.back().edge_val;
    std::vector<int> edge_to_bucket(static_cast<std::size_t>(max_edge + 1), -1);
    for (std::size_t b = 0; b < static_cast<std::size_t>(B); ++b)
        edge_to_bucket[static_cast<std::size_t>(buckets[b].edge_val)] =
            static_cast<int>(b);

    // Per-bucket match count (for Vitter's algorithm)
    std::vector<long long> bucket_matched(static_cast<std::size_t>(B), 0LL);

    std::mt19937_64 rng(seed);

    {
        std::ifstream in(input_path, std::ios::binary);
        static char buf2[IO_BUF];
        in.rdbuf()->pubsetbuf(buf2, sizeof(buf2));
        std::string skip; std::getline(in, skip);

        std::string line;
        long long total_lines = 0;
        long long file_row    = 0;  // row index among matching rows (for stable sort)

        while (std::getline(in, line)) {
            ++total_lines;
            if (progress && total_lines % REPORT_EVERY == 0)
                std::cerr << "  pass2: " << total_lines / 1'000'000 << "M rows\n";

            if (target_chromatic != -1 &&
                parse_chromatic(line.c_str()) != target_chromatic)
                continue;

            int e = parse_num_edges(line.c_str());
            if (e < 0 || e > max_edge) continue;

            int b = edge_to_bucket[static_cast<std::size_t>(e)];
            if (b < 0) continue;

            auto ub        = static_cast<std::size_t>(b);
            long long q    = buckets[ub].quota;
            long long& m   = bucket_matched[ub];
            ++m;

            if (static_cast<long long>(reservoirs[ub].size()) < q) {
                reservoirs[ub].push_back({file_row, line});
            } else if (q > 0) {
                std::uniform_int_distribution<long long> dist(0, m - 1);
                long long j = dist(rng);
                if (j < q)
                    reservoirs[ub][static_cast<std::size_t>(j)] = {file_row, line};
            }
            ++file_row;
        }
    }

    // ---- Merge all reservoirs, sort by original file order, write ---------
    std::vector<Slot> all;
    all.reserve(static_cast<std::size_t>(total_sampled));
    for (auto& r : reservoirs)
        for (auto& s : r)
            all.push_back(std::move(s));

    std::sort(all.begin(), all.end(),
              [](const Slot& a, const Slot& b) { return a.idx < b.idx; });

    out << header << '\n';
    for (const Slot& s : all)
        out << s.line << '\n';

    if (progress) {
        std::cerr << "  written " << all.size() << " rows\n";
        std::cerr << "  per-bucket breakdown (edge_val: sampled/total):\n";
        for (std::size_t b = 0; b < static_cast<std::size_t>(B); ++b)
            std::cerr << "    num_edges=" << buckets[b].edge_val
                      << ": " << reservoirs[b].size()
                      << " / " << buckets[b].count << "\n";
    }
}

// --------------------------------------------------------------------------
// Sequential mode: copy the first `limit` matching lines (-1 = unlimited).
// --------------------------------------------------------------------------
static long long run_sequential(
    std::ifstream& in,
    std::ofstream& out,
    const std::string& header,
    int target_chromatic,
    long long limit,
    bool progress)
{
    out << header << '\n';

    std::string line;
    long long total_lines = 0;
    long long matched     = 0;
    long long written     = 0;

    constexpr long long REPORT_EVERY = 50'000'000LL;

    while (std::getline(in, line)) {
        ++total_lines;
        if (progress && total_lines % REPORT_EVERY == 0)
            std::cerr << "  scanned " << total_lines / 1'000'000 << "M rows, "
                      << "matched " << matched << " ...\n";

        if (parse_chromatic(line.c_str()) != target_chromatic)
            continue;

        ++matched;

        if (limit == -1 || written < limit) {
            out << line << '\n';
            ++written;
            if (limit != -1 && written == limit) {
                if (progress)
                    std::cerr << "  reached --max " << limit << " after "
                              << total_lines << " rows scanned\n";
                break;
            }
        }
    }

    return matched;
}

// --------------------------------------------------------------------------
// Reservoir sampling (Vitter Algorithm R).
// --------------------------------------------------------------------------
static long long run_reservoir(
    std::ifstream& in,
    std::ofstream& out,
    const std::string& header,
    int target_chromatic,
    long long reservoir_size,
    uint64_t seed,
    bool progress)
{
    std::mt19937_64 rng(seed);

    struct Slot { long long idx; std::string line; };
    std::vector<Slot> reservoir;
    reservoir.reserve(static_cast<std::size_t>(reservoir_size));

    std::string line;
    long long total_lines = 0;
    long long matched     = 0;

    constexpr long long REPORT_EVERY = 50'000'000LL;

    while (std::getline(in, line)) {
        ++total_lines;
        if (progress && total_lines % REPORT_EVERY == 0)
            std::cerr << "  scanned " << total_lines / 1'000'000 << "M rows, "
                      << "matched " << matched << " ...\n";

        if (parse_chromatic(line.c_str()) != target_chromatic)
            continue;

        ++matched;

        if (static_cast<long long>(reservoir.size()) < reservoir_size) {
            reservoir.push_back({matched - 1, line});
        } else {
            std::uniform_int_distribution<long long> dist(0, matched - 1);
            long long j = dist(rng);
            if (j < reservoir_size)
                reservoir[static_cast<std::size_t>(j)] = {matched - 1, line};
        }
    }

    std::sort(reservoir.begin(), reservoir.end(),
              [](const Slot& a, const Slot& b) { return a.idx < b.idx; });

    out << header << '\n';
    for (const Slot& s : reservoir)
        out << s.line << '\n';

    return matched;
}

// --------------------------------------------------------------------------
// main
// --------------------------------------------------------------------------
int main(int argc, char** argv)
{
    Config cfg = parse_args(argc, argv);

    if (cfg.auto_seed) {
        std::random_device rd;
        cfg.seed = (static_cast<uint64_t>(rd()) << 32) | rd();
    }

    std::ifstream in(cfg.input_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open input: " << cfg.input_path << "\n";
        return 1;
    }
    static char read_buf[IO_BUF];
    in.rdbuf()->pubsetbuf(read_buf, sizeof(read_buf));

    std::string header;
    if (!std::getline(in, header)) {
        std::cerr << "error: input file is empty or unreadable\n";
        return 1;
    }
    if (!header.empty() && header.back() == '\r')
        header.pop_back();

    // --edge-stats: no output file
    if (cfg.edge_stats) {
        if (cfg.progress) {
            std::cerr << "Input:    " << cfg.input_path << "\n"
                      << "Mode:     edge-stats\n"
                      << "Chromatic filter: "
                      << (cfg.chromatic_set ? std::to_string(cfg.chromatic) : "all")
                      << "\n\n";
        }
        auto t0 = std::time(nullptr);
        run_edge_stats(in, cfg.chromatic, cfg.progress);
        if (cfg.progress)
            std::cerr << "\nDone in "
                      << static_cast<long long>(std::difftime(std::time(nullptr), t0))
                      << "s\n";
        return 0;
    }

    std::ofstream out(cfg.output_path);
    if (!out) {
        std::cerr << "error: cannot open output: " << cfg.output_path << "\n";
        return 1;
    }

    if (cfg.progress) {
        std::cerr << "Input:      " << cfg.input_path  << "\n"
                  << "Output:     " << cfg.output_path << "\n"
                  << "Chromatic:  " << cfg.chromatic   << "\n";
        if (cfg.max_count != -1)
            std::cerr << "Mode:       sequential, first " << cfg.max_count << "\n";
        else if (cfg.random_n != -1)
            std::cerr << "Mode:       reservoir, N=" << cfg.random_n
                      << ", seed=" << cfg.seed << "\n";
        else if (cfg.stratified_n != -1)
            std::cerr << "Mode:       stratified-edges, N=" << cfg.stratified_n
                      << ", seed=" << cfg.seed << "\n";
        else
            std::cerr << "Mode:       all matching\n";
        std::cerr << "\n";
    }

    auto t0 = std::time(nullptr);
    long long matched = 0;

    if (cfg.stratified_n != -1) {
        // stratified mode reopens the file internally for two passes
        run_stratified_edges(cfg.input_path, out, header,
                             cfg.chromatic, cfg.stratified_n, cfg.seed, cfg.progress);
    } else if (cfg.random_n != -1) {
        matched = run_reservoir(in, out, header,
                                cfg.chromatic, cfg.random_n, cfg.seed, cfg.progress);
    } else {
        matched = run_sequential(in, out, header,
                                 cfg.chromatic, cfg.max_count, cfg.progress);
    }

    out.close();
    auto elapsed = std::difftime(std::time(nullptr), t0);

    if (cfg.progress && cfg.stratified_n == -1) {
        long long written;
        if (cfg.random_n != -1)
            written = std::min(matched, cfg.random_n);
        else if (cfg.max_count != -1)
            written = std::min(matched, cfg.max_count);
        else
            written = matched;

        std::cerr << "\nDone in " << static_cast<long long>(elapsed) << "s\n"
                  << "  Total matching (chromatic=" << cfg.chromatic << "): "
                  << matched << "\n"
                  << "  Written to " << cfg.output_path << ": " << written << "\n";
    } else if (cfg.progress) {
        std::cerr << "\nDone in " << static_cast<long long>(elapsed) << "s\n"
                  << "  Written to " << cfg.output_path << "\n";
    }

    return 0;
}
