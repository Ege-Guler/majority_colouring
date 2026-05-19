import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Configuration
CSV_PATH = str(_ROOT / "notebooks" / "results_6vertex.csv")
CHUNK_SIZE = 1_000_000  # 1 million rows per chunk to save memory

if not os.path.exists(CSV_PATH):
    print(f"Error: {CSV_PATH} not found. Please run the enumeration script first.")
    sys.exit(1)

print(f"Starting chunked analysis of {CSV_PATH}...")

# Aggregation variables
chromatic_counts = {}
total_rows_processed = 0

# We'll use chunking to avoid loading the 38GB file into RAM
try:
    reader = pd.read_csv(CSV_PATH, chunksize=CHUNK_SIZE)
    
    for i, chunk in enumerate(reader):
        total_rows_processed += len(chunk)
        
        # Aggregate chromatic counts
        counts = chunk['chromatic_number'].value_counts().to_dict()
        for k, v in counts.items():
            chromatic_counts[k] = chromatic_counts.get(k, 0) + v
            
        if (i + 1) % 10 == 0:
            print(f"Processed {(i + 1) * CHUNK_SIZE / 1_000_000:.0f}M rows...")

except Exception as e:
    print(f"An error occurred during processing: {e}")
    sys.exit(1)

print("\n--- Analysis Complete ---")
print(f"Total weakly connected graphs analyzed: {total_rows_processed:,}")

# Print 3 and 4 color counts specifically
print("\nDistribution of Chromatic Numbers:")
for k in sorted(chromatic_counts.keys()):
    if k == -1:
        continue
    count = chromatic_counts[k]
    print(f"  {k} colors: {count:,} graphs")

# Visualization
sns.set_theme(style='whitegrid', palette='muted')
plt.figure(figsize=(10, 6))

keys = sorted([k for k in chromatic_counts.keys() if k != -1])
values = [chromatic_counts[k] for k in keys]

ax = sns.barplot(x=keys, y=values)
plt.title(f"Distribution of Majority Chromatic Number (N=6)", fontsize=14)
plt.xlabel("Chromatic Number", fontsize=12)
plt.ylabel("Number of Graphs (log scale)", fontsize=12)
plt.yscale('log')  # Log scale since the number of 2-colorable graphs is likely dominant

# Add text labels on top of bars
for i, v in enumerate(values):
    ax.text(i, v, f'{v:,}', color='black', ha="center", va="bottom", fontsize=10)

_vis_dir = _ROOT / "results" / "visualizations"
_vis_dir.mkdir(parents=True, exist_ok=True)
output_plot = str(_vis_dir / "chromatic_dist_6vertex.png")
plt.savefig(output_plot)
print(f"\nDistribution plot saved to: {output_plot}")
