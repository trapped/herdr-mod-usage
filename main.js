import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { exec, theme, props, appHome, layout, run } from "herdr";

// Remaining quota for each subscription, one bar per rate-limit window.
// Accounts come from usage.json in the app's home (see usage.example.json). fetch.py does the
// reading. sync.py puts the block (layout.json) into a layout derived from Herdr's current
// `main`: layouts/main-mods.json.

const REFRESH_MS = 5 * 60 * 1000;
const ROW = 18;
const PAD = 8;
const GAP = 5; // between accounts
// Each agent's brand colour (Herdr's program table only has monochrome tiles). An account's
// `color` in usage.json overrides it.
const BRAND = { claude: "#d97757", codex: "#10a37f" };

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}

function until(resets) {
  if (!resets) return "";
  const mins = Math.max(0, Math.round((resets - Date.now() / 1000) / 60));
  if (mins >= 2880) return `resets in ${Math.round(mins / 1440)}d`;
  if (mins >= 120) return `resets in ${Math.round(mins / 60)}h`;
  return `resets in ${mins}m`;
}

export default class Usage extends View {
  init(_props, cx) {
    try { this.data = JSON.parse(localStorage.getItem("usage") ?? "null"); } catch { this.data = null; }
    // Herdr updates its `main` layout but never a copy: rebuild ours from it on every start.
    cx.spawn(async () => {
      try {
        const r = await exec("python3", [`${appHome()}/mods/usage/sync.py`]);
        if (r.code !== 0) console.log(r.stderr.trim());
      } catch (e) { console.log(`usage: ${e}`); }
    });
    cx.timer.every(REFRESH_MS, (cx) => this.refresh(cx));
    this.refresh(cx);
  }

  refresh(cx) {
    if (this.busy) return;
    this.busy = true;
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", [`${appHome()}/mods/usage/fetch.py`, `${appHome()}/usage.json`], { timeout: 60000 });
        const data = JSON.parse(r.stdout);
        // A failed read keeps the last good bars, marked stale, rather than blanking the row.
        for (const a of data.accounts) {
          const old = this.data?.accounts?.find((o) => o.label === a.label);
          if (a.error && old?.bars?.length) { a.bars = old.bars; a.at = old.at ?? this.data.at; } else a.at = data.at;
        }
        this.data = data;
        localStorage.setItem("usage", JSON.stringify(data));
      } catch (e) {
        console.log(`usage: ${e}`);
      }
      this.busy = false;
      cx.notify();
    });
  }

  render() {
    const t = theme();
    const collapsed = (find(layout(), "sidebar")?.size?.px ?? Infinity) < 160;
    const rows = [];
    for (const a of this.data?.accounts ?? []) {
      if (!a.bars.length) rows.push({ label: a.label, error: a.error ?? "no data" });
      a.bars.forEach((b, i) => rows.push({ label: i === 0 ? a.label : "", account: a.label, color: a.color ?? BRAND[a.kind], stale: Boolean(a.error), error: a.error, ...b }));
    }

    // The block is as tall as its rows: ask the layout to follow when the count changes.
    const id = props()?.block;
    const gaps = rows.filter((r, i) => i > 0 && r.label).length;
    const want = Math.max(1, rows.length) * ROW + gaps * GAP + PAD * 2 + 1;
    if (id && rows.length && find(layout(), id)?.size?.px !== want) run("layout.resize", { id, px: want });

    const root = v_flex().size_full().bg(t.chrome).border_t(1).border_color(t.border).px(collapsed ? 6 : 16).py(PAD).text_size(11.5);
    if (!rows.length) return root.justify_center().text_color(t.dim).child(collapsed ? "" : (this.data ? "No accounts configured" : "Reading quota…"));

    return root.children(rows.map((r, i) => {
      const left = r.error && r.used === undefined ? null : Math.max(0, Math.min(100, 100 - r.used));
      const color = left === null || r.stale ? t.dim : left < 10 ? t.blocked : (r.color ?? t.accent);
      const tip = left === null ? `${r.label}: ${r.error}`
        : `${r.account} ${r.name}: ${Math.round(left)}% left${r.resets ? `, ${until(r.resets)}` : ""}${r.stale ? ` (stale: ${r.error})` : ""}`;
      const bar = h_flex().flex_1().h(4).rounded(2).overflow_hidden().bg(t.border)
        .when(left !== null && left > 0, (el) => el.child(div().h_full().flex_basis(0).flex_grow(left).bg(color)))
        .when(left !== null && left < 100, (el) => el.child(div().h_full().flex_basis(0).flex_grow(100 - left)));
      const row = h_flex().id(`u-${i}`).h(ROW).flex_none().gap(8).items_center().tooltip(tip).when(i > 0 && Boolean(r.label), (el) => el.mt(GAP));
      if (collapsed) return row.child(bar);
      return row
        .child(div().w(76).flex_none().truncate().text_color(t.muted).child(r.label))
        .child(div().w(34).flex_none().truncate().text_color(t.dim).child(r.name ?? ""))
        .child(left === null ? div().flex_1().truncate().text_color(t.dim).child(r.error) : bar)
        .when(left !== null, (el) => el.child(div().w(30).flex_none().flex().justify_end().text_color(r.stale ? t.dim : t.muted).child(`${Math.round(left)}%`)));
    }));
  }
}
