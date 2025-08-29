# save as: MsgDotTest.py
# usage (no args needed):
#   python "C:/Users/go25vol/Downloads/MsgDotTest.py"
#   neato -n2 -Tsvg out.dot -o out.svg
#
# Writes a DOT with FR coordinates and domain-colored nodes (no labels).
# First two domains are colored RED and BLUE (in that order), others follow a palette.

import os, re, sys
import networkx as nx
from collections import Counter

try:
    import extract_msg
except ImportError:
    print("Please: pip install extract-msg python-dateutil extract-msg", file=sys.stderr)
    sys.exit(1)

# === Hardcoded defaults (adjust if you like) ===
DEFAULT_INPUT  = r"C:\Users\go25vol\OneDrive - TUM\Github\AImAT\cartel-detector\mails\0_inbox_raw"
DEFAULT_OUTPUT = "out.dot"
DEFAULT_MIN_COUNT = 1
FR_SEED = 42
SCALE  = 1000.0  # scale FR coordinates to DOT space
# ==============================================

# 10-color palette (first two are enforced red, blue as required)
# Remaining 8 are pleasant distinct colors.
PALETTE = [
    "#e63946",  # red
    "#457b9d",  # blue
    "#f4a261",  # orange
    "#2a9d8f",  # teal/green
    "#8d99ae",  # gray-blue
    "#e9c46a",  # yellow
    "#a29bfe",  # light purple
    "#ef476f",  # pink
    "#06d6a0",  # mint
    "#118ab2",  # cyan
]

def clean_path(p: str) -> str:
    # strip surrounding quotes and normalize environment/tilde
    return os.path.normpath(os.path.expanduser(os.path.expandvars(p.strip().strip('"').strip("'"))))

def split_addresses(addr_field: str):
    if not addr_field:
        return []
    parts = re.split(r'[;,\n]+', addr_field)
    out = []
    for p in parts:
        p = p.strip().strip('"')
        if not p:
            continue
        m = re.search(r'<([^>]+)>', p)
        out.append((m.group(1) if m else p).lower())
    return out

def get_sender_email(msg):
    for attr in ("sender_email","sender","from_"):
        val = getattr(msg, attr, None)
        if isinstance(val, str) and "@" in val:
            m = re.search(r'<([^>]+)>', val)
            return (m.group(1) if m else val).lower()
    return ""

def scan_msgs(folder):
    paths = []
    for root, _, fns in os.walk(folder):
        for fn in fns:
            if fn.lower().endswith(".msg"):
                paths.append(os.path.join(root, fn))
    return paths

def domain_of(email: str) -> str:
    return email.split("@",1)[1] if "@" in email else "unknown"

def build_graph(paths):
    G = nx.Graph()
    for path in paths:
        try:
            msg = extract_msg.Message(path)
            sender = get_sender_email(msg)
            if not sender:
                continue
            tos = split_addresses(getattr(msg, "to", "") or "")
            ccs = split_addresses(getattr(msg, "cc", "") or "")
            for rcpt in tos + ccs:
                if rcpt and rcpt != sender:
                    # Use simple unweighted edges; FR will still space by structure
                    if G.has_edge(sender, rcpt):
                        # keep a lightweight weight counter if you want to filter later
                        G[sender][rcpt]["weight"] = G[sender][rcpt].get("weight", 1) + 1
                    else:
                        G.add_edge(sender, rcpt, weight=1)
        except Exception as e:
            print("Warning:", path, e, file=sys.stderr)
    return G

def fr_layout_fixed(G, min_count=1, seed=FR_SEED, scale=SCALE):
    """Return positions scaled and flipped for DOT pos attribute."""
    H = nx.Graph()
    for u, v, d in G.edges(data=True):
        if d.get("weight", 1) >= min_count:
            H.add_edge(u, v, weight=d.get("weight", 1))
    if H.number_of_nodes() == 0:
        return {}, H

    pos = nx.spring_layout(H, seed=seed, weight="weight", dim=2)
    # Normalize to [-0.5,0.5] then scale; invert Y to match screen coords
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    rangex = (maxx - minx) or 1.0
    rangey = (maxy - miny) or 1.0

    fixed = {}
    for n, (x, y) in pos.items():
        nx0 = (x - minx) / rangex - 0.5
        ny0 = (y - miny) / rangey - 0.5
        fixed[n] = (nx0 * scale, -ny0 * scale)
    return fixed, H

def assign_domain_colors(nodes):
    """Deterministically assign colors per domain. First two domains get red, blue."""
    dom_counts = Counter(domain_of(n) for n in nodes)
    # Sort by frequency desc, then name asc for stability
    ordered_domains = sorted(dom_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    # Map up to 10 domains to palette; others fall back to gray
    mapping = {}
    for i, (dom, _) in enumerate(ordered_domains):
        color = PALETTE[i] if i < len(PALETTE) else "#BDBDBD"
        mapping[dom] = color
    return mapping

def write_dot(out_path, H, pos, min_count=DEFAULT_MIN_COUNT):
    deg = dict(H.degree())
    domain_color = assign_domain_colors(H.nodes())

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("graph EmailGraph {\n")
        # Hints for neato-based rendering with fixed positions
        f.write("  model=subset;\n")
        f.write("  mode=ipsep;\n")
        f.write("  overlap=false;\n")
        f.write("  splines=true;\n")
        f.write("  outputorder=edgesfirst;\n")
        # Minimalist default node style (individual nodes override fillcolor/size)
        f.write('  node [shape=circle, style=filled, label="", color=none];\n')
        f.write('  edge [color="#B0B0B0", penwidth=0.5];\n')

        # Nodes with fixed FR positions, sized by degree, colored by domain
        for n, (x, y) in pos.items():
            dom = domain_of(n)
            col = domain_color.get(dom, "#BDBDBD")
            size = max(0.12, deg.get(n, 1) * 0.05)  # inches; fixedsize circles
            # use fixedsize=true so width is respected; pos uses "!"
            f.write(f'  "{n}" [pos="{x:.2f},{y:.2f}!", fixedsize=true, width={size:.2f}, fillcolor="{col}"];\n')

        # Edges (undirected)
        for u, v in H.edges():
            f.write(f'  "{u}" -- "{v}";\n')

        f.write("}\n")

def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("input_folder", nargs="?", help="Folder containing .msg files")
    ap.add_argument("out_folder", nargs="?", help="Folder where mail_graph.dot will be saved")
    ap.add_argument("--min-count", type=int, default=1)
    args = ap.parse_args()

    # Ask interactively if missing
    if not args.input_folder:
        args.input_folder = input("Enter folder containing .msg files: ").strip()
    if not args.out_folder:
        args.out_folder = input("Enter folder where output should be saved: ").strip()

    # Clean & normalize paths
    args.input_folder = clean_path(args.input_folder)
    args.out_folder = clean_path(args.out_folder)

    # Ensure output folder exists
    if not os.path.isdir(args.out_folder):
        print(f"Output folder does not exist: {args.out_folder}", file=sys.stderr)
        sys.exit(3)

    out_dot = os.path.join(args.out_folder, "mail_graph.dot")

    paths = scan_msgs(args.input_folder)
    print(f"Scanning: {args.input_folder}")
    print(f"Found {len(paths)} .msg files")

    if not paths:
        print("No .msg files found.", file=sys.stderr)
        sys.exit(2)

    G = build_graph(paths)
    pos, H = fr_layout_fixed(G, min_count=args.min_count, seed=FR_SEED, scale=SCALE)
    if not pos:
        print("Graph is empty after filtering; nothing to write.", file=sys.stderr)
        sys.exit(3)

    write_dot(out_dot, H, pos, min_count=args.min_count)
    print(f"\n✅ Wrote {out_dot}\nRender with:\n  neato -n2 -Tsvg {out_dot} -o mail_graph.svg")


if __name__ == "__main__":
    main()
