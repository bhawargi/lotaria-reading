# GRIEF
# This is not working as I expect it to be.

import os
import string
import csv
from collections import Counter
from ebooklib import epub
import matplotlib.pyplot as plt

def extract_text_from_epub(filename):
    try:
        book = epub.read_epub(filename)
        text = ''

        # Extract text content from the EPUB
        for item in book.get_items():
            if item.get_type() == epub.EpubHtml:
                # Decode the item content with fallback to replace characters
                item_text = item.get_body_content().decode('utf-8', 'replace')
                text += item_text

        return text

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return None
    except Exception as e:
        print(f"Error parsing EPUB file: {e}")
        return None

def analyze_epub_file(filename):
    if filename.endswith('.epub'):
        # Handle EPUB file
        text = extract_text_from_epub(filename)
        if text:
            analyze_text(text, filename)
    else:
        # Not an EPUB file
        pass  # Do nothing or handle accordingly

def analyze_text(content, filename):
    # Remove punctuation and convert to lowercase
    content = content.translate(str.maketrans('', '', string.punctuation)).lower()

    # Word frequency analysis
    words = content.split()
    word_freq = Counter(words)

    # Plotting top 50 words
    top_words = word_freq.most_common(50)
    words, frequencies = zip(*top_words)

    plt.figure(figsize=(10, 8))
    plt.barh(words, frequencies)
    plt.gca().invert_yaxis()  # Invert y-axis to have the most common word on top
    plt.xlabel('Frequency')
    plt.ylabel('Words')
    plt.title('Top 50 Words Frequency')
    plt.tight_layout()

    # Save plot to 'results' subfolder
    results_folder = 'results'
    if not os.path.exists(results_folder):
        os.makedirs(results_folder)

    plot_filename = os.path.join(results_folder, f"{os.path.splitext(os.path.basename(filename))[0]}_top_words.png")
    plt.savefig(plot_filename)
    print(f"Plot saved to '{plot_filename}'")

    plt.show()

    # Export to CSV
    export_to_csv(word_freq, filename)

def export_to_csv(word_freq, filename):
    # Construct the CSV file path
    results_folder = 'results'
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
