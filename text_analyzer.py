import string
import os
import sys
import csv
from collections import Counter
import matplotlib.pyplot as plt

def analyze_text(content):
    content = content.translate(str.maketrans('', '', string.punctuation)).lower()

    # Word frequency analysis
    words = content.split()
    word_freq = Counter(words)

    return word_freq

def analyze_text_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            text = file.read()
            word_freq = analyze_text(text)

            top_words = word_freq.most_common(50)
            words, frequencies = zip(*top_words)

            plt.figure(figsize=(10, 8))
            plt.barh(words, frequencies)
            plt.gca().invert_yaxis()
            plt.xlabel('Frequency')
            plt.ylabel('Words')
            plt.title('Top 50 Words Frequency')
            plt.tight_layout()
            plt.show()

            return word_freq

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return None

def export_to_csv(word_freq, filename):
    results_folder = 'results'
    if not os.path.exists(results_folder):
        os.makedirs(results_folder)

    filename = filename = sys.argv[1]
    csv_filename = os.path.join(results_folder, f"{os.path.splitext(os.path.basename(filename))[0]}_word_frequency.csv")

    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['Word', 'Frequency'])
            for word, freq in word_freq.most_common():
                csv_writer.writerow([word, freq])
        
        print(f"Word frequency data exported to '{csv_filename}'")

    except IOError:
        print(f"Error writing to CSV file '{csv_filename}'")