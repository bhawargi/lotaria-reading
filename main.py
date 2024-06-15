import sys
# from os.path import exists, remove
from epub_handler import analyze_epub_file
from epub2txt import epub2txt
from text_analyzer import analyze_text_file, export_to_csv

def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <file_name>")
        return

    filename = sys.argv[1]

    if filename.endswith(".epub"):
        print("was here")
        extracted_text = epub2txt(filename)
        with open("books/tmp.txt", "w") as file:
            file.write(extracted_text)
        filename="books/tmp.txt"

    text_freq = analyze_text_file(filename)
    if text_freq:
        export_to_csv(text_freq, filename)
        # analyze_epub_file(filename)

    # if exists("books/tmp.txt"):
    #     remove("books/tmp.txt")

if __name__ == "__main__":
    main()
