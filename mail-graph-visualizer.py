import os, re, sys
import networkx as nx
from collections import Counter

try:
    import extract_msg
except ImportError:
    print("Please: pip install networkx extract-msg python-dateutil", file=sys.stderr)
    sys.exit(1)

# === Defaults ===
DEFAULT_OUTPUT = "mail_graph.dot"
FR_SEED = 42
SCALE  = 1000.0  # scale FR coordinates to DOT space
# =================

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

def write_dot(out_path, H, pos, min_count=1):
    # Node strength = total correspondence volume (sum of incident edge weights)
    strength = dict(H.degree(weight="weight"))
    domain_color = assign_domain_colors(H.nodes())

    # Normalize node sizes
    if strength:
        s_vals = list(strength.values())
        s_min, s_max = min(s_vals), max(s_vals)
        s_range = (s_max - s_min) or 1.0
    else:
        s_min, s_range = 0.0, 1.0
    node_min, node_max = 0.18, 0.90  # inches

    # Edge penwidth/transparency scaling by weight
    e_weights = [d.get("weight", 1) for _, _, d in H.edges(data=True)]
    if e_weights:
        w_min, w_max = min(e_weights), max(e_weights)
        w_range = (w_max - w_min) or 1.0
    else:
        w_min, w_range = 1.0, 1.0
    edge_min, edge_max = 0.5, 3.0
    # Alpha range: compress more; keep even strong edges fairly transparent
    alpha_min, alpha_max = 50, 90  # 0..255

    # Node transparency scaling by correspondence volume (strength)
    node_alpha_min, node_alpha_max = 140, 255  # 0..255 (small nodes more transparent)

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

        # Nodes: fixed positions, sized by correspondence volume, colored by domain (with alpha)
        for n, (x, y) in pos.items():
            dom = domain_of(n)
            base = domain_color.get(dom, "#BDBDBD")
            s = strength.get(n, 0.0)
            size = node_min + ((s - s_min) / s_range) * (node_max - node_min)
            na = int(node_alpha_min + ((s - s_min) / s_range) * (node_alpha_max - node_alpha_min))
            na = max(0, min(255, na))
            # Append alpha to base color (#RRGGBB -> #RRGGBBAA)
            col = f"{base}{na:02X}"
            f.write(f'  "{n}" [pos="{x:.2f},{y:.2f}!", fixedsize=true, width={size:.2f}, fillcolor="{col}"];\n')

        # Edges: width encodes correspondence weight; color uses RGBA with weight-based alpha
        for u, v, d in H.edges(data=True):
            w = d.get("weight", 1)
            pen = edge_min + ((w - w_min) / w_range) * (edge_max - edge_min)
            a = int(alpha_min + ((w - w_min) / w_range) * (alpha_max - alpha_min))
            a = max(0, min(255, a))
            # Base gray edge color with alpha
            col = f"#707070{a:02X}"
            f.write(f'  "{u}" -- "{v}" [penwidth={pen:.2f}, color="{col}"];\n')

        f.write("}\n")

def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("input_folder", nargs="?", help="Folder containing .msg files")
    ap.add_argument("out_folder", nargs="?", help="Folder where mail_graph.dot will be saved")
    # Optional flags for convenience
    ap.add_argument("-i", "--input", dest="input_folder", help="Folder containing .msg files")
    ap.add_argument("-o", "--out", dest="out_folder", help="Folder to save outputs (DOT)")
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

    # Ensure output folder exists (create if missing)
    if not os.path.isdir(args.out_folder):
        os.makedirs(args.out_folder, exist_ok=True)

    out_dot = os.path.join(args.out_folder, DEFAULT_OUTPUT)

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
    print(f"\n? Wrote {out_dot}\nRender with:\n  neato -n2 -Tsvg {out_dot} -o mail_graph.svg")


if __name__ == "__main__":
    main()
