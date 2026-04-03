import tkinter as tk
from tkinter import messagebox
import networkx as nx
import math


class GraphDrawer:
    def __init__(self, root):
        self.root = root
        self.root.title("Planar Grapher: Unified Control")

        # --- UI Setup ---
        self.toolbar = tk.Frame(root, bg="#e8e8e8", bd=1, relief=tk.RAISED)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        self.btn_mode = tk.Button(self.toolbar, text="MODE: VERTEX", width=20,
                                  command=self.cycle_mode, bg="#d1d1d1")
        self.btn_mode.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_relax = tk.Button(self.toolbar, text="Auto-Layout", command=self.relax_graph)
        self.btn_relax.pack(side=tk.LEFT, padx=5, pady=5)

        self.status_label = tk.Label(root, text="VERTEX: L-Click to add | Drag to move | 'D' to delete",
                                     bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(root, width=800, height=600, bg="white", highlightthickness=0)
        self.canvas.pack(pady=10)

        # --- Logic State ---
        self.modes = ["VERTEX", "EDGE", "ROUTE/EDIT"]
        self.current_mode_idx = 0

        self.nodes = []  # [[x, y, id]]
        self.edges = []  # [{"u": idx, "v": idx, "type": "+", "cx": x, "cy": y}]

        self.selected_node = None
        self.active_element = None  # Index of node or edge being focused
        self.default_type = "+"

        # --- Bindings ---
        self.canvas.bind("<Button-1>", self.handle_press)
        self.canvas.bind("<B1-Motion>", self.handle_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_release)
        self.root.bind("t", lambda e: self.toggle_edge_type())
        self.root.bind("T", lambda e: self.toggle_edge_type())
        self.root.bind("d", lambda e: self.delete_element())
        self.root.bind("D", lambda e: self.delete_element())
        self.root.bind("<space>", lambda e: self.cycle_mode())

    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(self.modes)
        self.selected_node = None
        self.active_element = None

        mode_name = self.modes[self.current_mode_idx]
        self.btn_mode.config(text=f"MODE: {mode_name}")

        messages = {
            "VERTEX": "Drag nodes to move | L-Click to add | 'D' to delete node.",
            "EDGE": "Click two nodes to connect. (Check for planarity)",
            "ROUTE/EDIT": "Drag orange points | 'T' to flip sign | 'D' to delete edge."
        }
        self.status_label.config(text=messages[mode_name])
        self.refresh_canvas()

    def handle_press(self, event):
        mode = self.modes[self.current_mode_idx]
        node_idx = self.find_closest_node(event.x, event.y)

        if mode == "VERTEX":
            if node_idx is not None:
                self.active_element = node_idx
            else:
                self.nodes.append([event.x, event.y, None])
                self.active_element = len(self.nodes) - 1  # Select the new node
            self.refresh_canvas()

        elif mode == "EDGE":
            if node_idx is not None:
                if self.selected_node is None:
                    self.selected_node = node_idx
                else:
                    self.attempt_add_edge(self.selected_node, node_idx)
                    self.selected_node = None
                self.refresh_canvas()

        elif mode == "ROUTE/EDIT":
            self.active_element = self.find_closest_edge_control(event.x, event.y)
            self.refresh_canvas()

    def handle_drag(self, event):
        mode = self.modes[self.current_mode_idx]
        if mode == "VERTEX" and self.active_element is not None:
            old_x, old_y = self.nodes[self.active_element][0], self.nodes[self.active_element][1]
            dx, dy = event.x - old_x, event.y - old_y
            self.nodes[self.active_element][0], self.nodes[self.active_element][1] = event.x, event.y
            for e in self.edges:
                if e["u"] == self.active_element or e["v"] == self.active_element:
                    e["cx"] += dx / 2
                    e["cy"] += dy / 2
            self.refresh_canvas()
        elif mode == "ROUTE/EDIT" and self.active_element is not None:
            self.edges[self.active_element]["cx"], self.edges[self.active_element]["cy"] = event.x, event.y
            self.refresh_canvas()

    def handle_release(self, event):
        # We keep the selection for Route and Vertex mode so 'D' or 'T' works
        pass

    def delete_element(self):
        mode = self.modes[self.current_mode_idx]
        if mode == "VERTEX" and self.active_element is not None:
            idx = self.active_element
            # Remove edges connected to this node
            self.edges = [e for e in self.edges if e["u"] != idx and e["v"] != idx]
            # Re-index remaining edges
            for e in self.edges:
                if e["u"] > idx: e["u"] -= 1
                if e["v"] > idx: e["v"] -= 1
            self.nodes.pop(idx)
            self.active_element = None
            self.refresh_canvas()

        elif mode == "ROUTE/EDIT" and self.active_element is not None:
            self.edges.pop(self.active_element)
            self.active_element = None
            self.refresh_canvas()

    def toggle_edge_type(self):
        if self.modes[self.current_mode_idx] == "ROUTE/EDIT" and self.active_element is not None:
            curr = self.edges[self.active_element]["type"]
            self.edges[self.active_element]["type"] = "-" if curr == "+" else "+"
            self.refresh_canvas()

    def attempt_add_edge(self, u, v):
        if u == v: return
        temp_g = nx.Graph()
        for e in self.edges: temp_g.add_edge(e["u"], e["v"])
        temp_g.add_edge(u, v)
        if not nx.check_planarity(temp_g)[0]:
            messagebox.showerror("Planarity Error", "This edge violates planarity.")
            return
        n1, n2 = self.nodes[u], self.nodes[v]
        cx, cy = (n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2
        self.edges.append({"u": u, "v": v, "type": self.default_type, "cx": cx, "cy": cy})

    def refresh_canvas(self):
        self.canvas.delete("all")
        mode = self.modes[self.current_mode_idx]
        for i, e in enumerate(self.edges):
            n1, n2 = self.nodes[e["u"]], self.nodes[e["v"]]
            is_sel = (mode == "ROUTE/EDIT" and i == self.active_element)
            color = "orange" if is_sel else ("blue" if e["type"] == "+" else "red")
            self.canvas.create_line(n1[0], n1[1], e["cx"], e["cy"], n2[0], n2[1],
                                    fill=color, dash=(None if e["type"] == "+" else (4, 4)),
                                    width=(4 if is_sel else 2), smooth=True)
            if mode == "ROUTE/EDIT":
                self.canvas.create_oval(e["cx"] - 5, e["cy"] - 5, e["cx"] + 5, e["cy"] + 5, fill="orange")

        for i, (x, y, _) in enumerate(self.nodes):
            is_active = (mode == "VERTEX" and i == self.active_element) or (mode == "EDGE" and i == self.selected_node)
            self.canvas.create_oval(x - 8, y - 8, x + 8, y + 8, fill=("yellow" if is_active else "black"),
                                    outline="white")

    def find_closest_node(self, x, y):
        for i, (nx_v, ny_v, _) in enumerate(self.nodes):
            if math.hypot(x - nx_v, y - ny_v) < 15: return i
        return None

    def find_closest_edge_control(self, x, y):
        for i, e in enumerate(self.edges):
            if math.hypot(x - e["cx"], y - e["cy"]) < 20: return i
        return None

    def relax_graph(self):
        if not self.nodes: return
        G = nx.Graph()
        G.add_nodes_from(range(len(self.nodes)))
        for e in self.edges: G.add_edge(e["u"], e["v"])
        pos = nx.spring_layout(G, k=2.0)
        for i, p in pos.items():
            self.nodes[i][0], self.nodes[i][1] = p[0] * 300 + 400, p[1] * 250 + 300
        for e in self.edges:
            n1, n2 = self.nodes[e["u"]], self.nodes[e["v"]]
            e["cx"], e["cy"] = (n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2
        self.refresh_canvas()


if __name__ == "__main__":
    root = tk.Tk()
    app = GraphDrawer(root)
    root.mainloop()