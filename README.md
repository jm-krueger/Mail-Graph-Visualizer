# Mail Graph Visualizer

This project extracts metadata from Outlook `.msg` files and builds a graph of senders and recipients.  
It outputs a **Graphviz `.dot` file** with a **Fruchterman–Reingold (spring) layout** baked in, so you can visualize the communication structure.

---

## Features
- Parses Outlook `.msg` files using [extract-msg](https://pypi.org/project/extract-msg/).
- Builds a communication network (senders ↔ recipients).
- Node positions precomputed with **Fruchterman–Reingold** layout.
- Nodes colored by **email domain** (up to 10 distinct colors).
- Outputs a single DOT file: `mail_graph.dot`.

---

## Requirements
- Python 3.9+  
- Install dependencies:
  ```bash
  pip install extract-msg python-dateutil networkx
  ```
- [Graphviz](https://graphviz.org/download/) installed and available in your PATH.

---

## Usage

Run the script:

```bash
python mail-graph-visualizer.py
```

You’ll be prompted for:
1. The folder containing `.msg` files.  
2. The folder where the result should be saved.  

The output file will always be called:

```
mail_graph.dot
```

---

## Rendering

Convert the DOT file to an SVG with Graphviz:

```bash
neato -n2 -Tsvg mail_graph.dot -o mail_graph.svg
```

or to a PNG:

```bash
neato -n2 -Tpng mail_graph.dot -o mail_graph.png
```

---

## Example

<img width="665" height="697" alt="image" src="https://github.com/user-attachments/assets/6de6af8e-c0e6-4dd9-9a6c-a644f5ecdca1" />



