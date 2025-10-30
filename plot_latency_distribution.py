import json
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rcParams

# Set font and style
rcParams['font.family'] = 'sans-serif'
rcParams['font.size'] = 14

# Read the JSON file
with open('outputs/tb_gen_tb_thinking_32B/evaluation_summary_v0.json', 'r') as f:
    data = json.load(f)

# Extract task numbers and latencies
task_numbers = []
latencies = []
detection_scores = []

for task in data['per_task_results']:
    task_numbers.append(task['task_number'])
    latencies.append(task['latency'])
    detection_scores.append(task['metrics']['golden_accuracy'])

# Create figure with two subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={'width_ratios': [3, 1]})

# Define colors (matching the reference image)
color_low = '#e8a5a5'  # Pink/coral for lower performance
color_high = '#7fb8c9'  # Blue/teal for higher performance

# Classify points based on detection score
colors = [color_high if score > 0 else color_low for score in detection_scores]

# Left plot: Scatter plot of latency vs problem index
ax1.scatter(task_numbers, latencies, c=colors, alpha=0.6, s=50, edgecolors='none')
ax1.set_xlabel('Problem Index', fontsize=16)
ax1.set_ylabel('Latency (s)', fontsize=16)
ax1.set_ylim(-5, max(latencies) * 1.05)
ax1.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
ax1.set_axisbelow(True)

# Right plot: Histogram of latency distribution
bins = np.linspace(0, max(latencies), 30)
latencies_low = [latencies[i] for i in range(len(latencies)) if detection_scores[i] == 0]
latencies_high = [latencies[i] for i in range(len(latencies)) if detection_scores[i] > 0]

# Stack histograms
ax2.hist(latencies_low, bins=bins, orientation='horizontal', color=color_low, alpha=0.7, edgecolor='none')
ax2.hist(latencies_high, bins=bins, orientation='horizontal', color=color_high, alpha=0.7, edgecolor='none')
ax2.set_xlabel('Count', fontsize=16)
ax2.set_ylabel('')
ax2.set_ylim(ax1.get_ylim())
ax2.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
ax2.set_axisbelow(True)

# Add legend
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor=color_low, label='Eval 1 = False'),
    Patch(facecolor=color_high, label='Eval 1 = True')
]
fig.legend(handles=legend_elements, loc='upper center', ncol=2, fontsize=14, 
           frameon=False, bbox_to_anchor=(0.5, 1.02))

# Adjust layout
plt.tight_layout(rect=[0, 0, 1, 0.96])

# Save the plot
output_path = 'figures/latency_distribution_plot.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"Plot saved to: {output_path}")

# Display statistics
print(f"\nLatency Statistics:")
print(f"Average latency: {data['latency_statistics']['average_latency']:.2f} s")
print(f"Min latency: {data['latency_statistics']['min_latency']:.2f} s")
print(f"Max latency: {data['latency_statistics']['max_latency']:.2f} s")
print(f"Total tasks: {data['latency_statistics']['total_tasks']}")
print(f"Successful detection: {len(latencies_high)}")
print(f"Failed detection: {len(latencies_low)}")

plt.show()

