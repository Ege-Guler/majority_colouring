import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Configuration
CSV_PATH = str(_ROOT / "notebooks" / "results_6vertex.csv")
OUTPUT_DIR = str(_ROOT / "results" / "visualizations_6vertex")
CHUNK_SIZE = 1_000_000  # 1 million rows per chunk to save memory

if not os.path.exists(CSV_PATH):
    print(f"Error: {CSV_PATH} not found. Please run the enumeration script first.")
    sys.exit(1)

os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Starting comprehensive chunked analysis of {CSV_PATH}...")

# Data containers for aggregation
chromatic_counts = {}
property_means_by_chromatic = {}
all_data_for_correlation = [] # We'll store a small sampled subset for correlation/plotting

# We use Reservoir Sampling or Systematic Sampling to get a manageable subset for plots
# 1M rows is plenty for visualization but small enough for 32GB RAM
SAMPLE_SIZE = 1_000_000
total_processed = 0

try:
    reader = pd.read_csv(CSV_PATH, chunksize=CHUNK_SIZE)
    
    for i, chunk in enumerate(reader):
        total_processed += len(chunk)
        
        # 1. Basic Counts
        counts = chunk['chromatic_number'].value_counts().to_dict()
        for k, v in counts.items():
            chromatic_counts[k] = chromatic_counts.get(k, 0) + v
            
        # 2. Grouped statistics (Running totals)
        # We only care about chromatic_number != -1
        valid_chunk = chunk[chunk['chromatic_number'] != -1]
        grouped = valid_chunk.groupby('chromatic_number').agg({
            'num_edges': ['sum', 'count'],
            'connectivity_number': 'sum',
            'stability_number': 'sum',
            'clique_number': 'sum'
        })
        
        for chrom, row in grouped.iterrows():
            if chrom not in property_means_by_chromatic:
                property_means_by_chromatic[chrom] = {
                    'count': 0, 'num_edges_sum': 0, 'connectivity_sum': 0,
                    'stability_sum': 0, 'clique_sum': 0
                }
            stats_dict = property_means_by_chromatic[chrom]
            stats_dict['count'] += row[('num_edges', 'count')]
            stats_dict['num_edges_sum'] += row[('num_edges', 'sum')]
            stats_dict['connectivity_sum'] += row[('connectivity_number', 'sum')]
            stats_dict['stability_sum'] += row[('stability_number', 'sum')]
            stats_dict['clique_sum'] += row[('clique_number', 'sum')]

        # 3. Systematic Sampling for Correlation/Plots (Keep every ~1000th row)
        sample_chunk = valid_chunk.iloc[::1000, :]
        all_data_for_correlation.append(sample_chunk)

        if (i + 1) % 10 == 0:
            print(f"Processed {(i + 1) * CHUNK_SIZE / 1_000_000:.0f}M rows...")

except Exception as e:
    print(f"An error occurred during processing: {e}")
    sys.exit(1)

# Combine sampled data
df_sample = pd.concat(all_data_for_correlation)
print(f"\nAnalysis complete. Total processed: {total_processed:,}")
print(f"Sample size for visualizations: {len(df_sample):,}")

# --- 1. Distribution of Chromatic Numbers (Log Scale) ---
plt.figure(figsize=(10, 6))
sns.set_theme(style='whitegrid', palette='muted')
keys = sorted([k for k in chromatic_counts.keys() if k != -1])
values = [chromatic_counts[k] for k in keys]
ax = sns.barplot(x=keys, y=values)
plt.yscale('log')
plt.title("Majority Chromatic Number Distribution (N=6)")
plt.xlabel("Chromatic Number")
plt.ylabel("Number of Graphs (log)")
for i, v in enumerate(values):
    ax.text(i, v, f'{v:,}', color='black', ha="center", va="bottom")
plt.savefig(os.path.join(OUTPUT_DIR, '01_chromatic_dist.png'))
plt.close()

# --- 2. Mean Properties by Chromatic Number ---
print("\nProperty Means by Chromatic Number:")
means_list = []
for chrom in sorted(property_means_by_chromatic.keys()):
    d = property_means_by_chromatic[chrom]
    n = d['count']
    row_means = {
        'chromatic_number': chrom,
        'avg_edges': d['num_edges_sum'] / n,
        'avg_connectivity': d['connectivity_sum'] / n,
        'avg_stability': d['stability_sum'] / n,
        'avg_clique': d['clique_sum'] / n
    }
    means_list.append(row_means)
    print(f"  {chrom} colors: {row_means}")

df_means = pd.DataFrame(means_list)
df_means.to_csv(os.path.join(OUTPUT_DIR, 'summary_stats.csv'), index=False)

# --- 3. Property Boxplots (Using Sample) ---
cols_to_plot = ['num_edges', 'connectivity_number', 'stability_number', 'clique_number']
fig, axes = plt.subplots(2, 2, figsize=(15, 12))
axes = axes.flatten()
for i, col in enumerate(cols_to_plot):
    sns.boxplot(x='chromatic_number', y=col, data=df_sample, ax=axes[i], palette='Set2')
    axes[i].set_title(f"{col.replace('_', ' ').title()} vs Chromatic Number")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, '02_property_boxplots.png'))
plt.close()

# --- 4. Correlation Heatmap (Using Sample) ---
plt.figure(figsize=(10, 8))
corr = df_sample[['chromatic_number'] + cols_to_plot].corr()
mask = np.triu(np.ones_like(corr, dtype=bool))
sns.heatmap(corr, mask=mask, annot=True, cmap='coolwarm', fmt=".2f")
plt.title("Correlation Matrix (N=6 Sample)")
plt.savefig(os.path.join(OUTPUT_DIR, '03_correlation_heatmap.png'))
plt.close()

# --- 5. Clique Number Joint Plot (Important correlation) ---
plt.figure(figsize=(10, 6))
sns.violinplot(x='chromatic_number', y='clique_number', data=df_sample, inner="quart", palette="Pastel1")
plt.title("Clique Number Distribution by Chromatic Number")
plt.savefig(os.path.join(OUTPUT_DIR, '04_clique_violin.png'))
plt.close()

print(f"\nIn-depth analysis finished. Visualizations saved to: {OUTPUT_DIR}")
print(f"Summary statistics saved to: {os.path.join(OUTPUT_DIR, 'summary_stats.csv')}")
