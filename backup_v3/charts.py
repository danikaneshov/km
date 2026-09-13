import matplotlib.pyplot as plt
import seaborn as sns
import uuid
import os
import matplotlib

# Use aggressive non-interactive backend to avoid GUI errors on Mac
matplotlib.use('Agg')

def setup_style():
    sns.set_theme(style="whitegrid")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['figure.figsize'] = (10, 6)
    plt.rcParams['axes.titlesize'] = 16
    plt.rcParams['axes.labelsize'] = 12

def draw_pie_chart(labels: list, sizes: list, title: str) -> str:
    """
    Draws a pie chart and saves it to a unique file.
    Returns the file path.
    """
    setup_style()
    fig, ax = plt.subplots()
    
    # Generate some nice colors
    colors = sns.color_palette('pastel')[0:len(labels)]
    
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, 
        autopct='%1.1f%%', startangle=140,
        wedgeprops={'edgecolor': 'white'}
    )
    
    # Improve text readability
    for text in texts:
        text.set_fontsize(10)
    for autotext in autotexts:
        autotext.set_fontsize(10)
        autotext.set_weight('bold')
        
    ax.set_title(title, pad=20)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    
    filename = f"chart_pie_{uuid.uuid4().hex[:8]}.png"
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    plt.close()
    
    return filename

def draw_bar_chart(labels: list, values: list, title: str, xlabel: str = "", ylabel: str = "") -> str:
    """
    Draws a bar chart and saves it to a unique file.
    Returns the file path.
    """
    setup_style()
    fig, ax = plt.subplots()
    
    colors = sns.color_palette('mako', n_colors=len(labels))
    sns.barplot(x=labels, y=values, ax=ax, palette=colors)
    
    ax.set_title(title, pad=20)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    
    # Rotate x labels if there are many of them or they are long
    if len(labels) > 5:
        plt.xticks(rotation=45, ha='right')
        
    filename = f"chart_bar_{uuid.uuid4().hex[:8]}.png"
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    plt.close()
    
    return filename
