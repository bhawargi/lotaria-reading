# Word Frequency Analysis

Inspired by the dialogue (*for shits and giggles!*)

> "What is the reading of a text, in fact, except the recording of certain thematic recurrences, certain insistences of form and meaning? An electronic reading supplies me with a list of frequencies, which I have only to glance at to form an idea of the problems the book suggests to my critical study."
> \- Lotaria \(from *If On A Winter's Night A Traveller*)


## Usage

* \[Sugggested\]: Run in a virtual environment to prevent package conflicts
```
$ python -m venv venv
$ source venv/bin/activate
```
* Install required packages
```
$ pip install -r requirements.txt
```
* Run main file
```
$ py main.py books/<filename>
OR
$ py main.py <filepath>
```

* Results are stored in the results folder as a CSV file, and the top 50 words are visualized as a bar graph.

## Misc

* Code works a little iffy with EPUB files, makes quick work of txt files.
* Code does not filter out articles, pronouns and particles. Head straight for the words richest in meaning; they can give a fairly precise notion of the book.
* Found a JS project that achieves a similar ask [mvximenko/wordy](https://github.com/mvximenko/wordy.git)
