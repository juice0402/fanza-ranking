// 所属事務所とSNS（data/agencies.json。scripts/agency_links.py が週1回、事務所の公式サイトから集める）の部品（画面に依存しない。tests/test_agencies.mjs）。
// 運営者の希望（2026-10-05）「所属を、所属先の公式的な情報から反映できないか。TwitterやインスタのリンクがあったらSNSも」。
// 載せるのは、事務所の公式サイトの所属女優のページに載っている所属とアカウントだけ（FANZA の名前と完全に同じ1人に結びついた人。推測はしない）。
// 事務所の名前・公式サイトは、下の AGENCIES だけを使う（scripts/agency_links.py の SITES と同じ。テストで突き合わせている）

export const AGENCIES = {
  tpowers: { name: 'ティーパワーズ', url: 'https://www.t-powers.co.jp/' },
  mines: { name: 'マインズ', url: 'https://mines-pro.jp/' },
  bambi: { name: 'バンビプロモーション', url: 'https://bambi.ne.jp/' },
  soagent: { name: 'SO MODELAGENT', url: 'https://so-agent.jp/' },
  alive: { name: 'プロダクションALIVE', url: 'https://alive-pro.tokyo/' },
  esflat: { name: 'エスフラート', url: 'http://www.style-1.jp/' },
  capsule: { name: 'カプセルエージェンシー', url: 'https://capsule.bz/' },
  cmore: { name: 'C-more ENTERTAINMENT', url: 'https://cmore.jp/official/' },
  light: { name: 'LIGHT promotion', url: 'https://lightpro.jp/' },
  life: { name: 'ライフプロモーション', url: 'https://life-promotion.com/' },
  linx: { name: 'LINX', url: 'https://pub.linx.live/' },
  nax: { name: 'NAX', url: 'https://official.nax-pro.com/' },
  duo: { name: 'Duo Entertainment', url: 'https://www.duo-official.com/' },
};

const X_HANDLE = /^[A-Za-z0-9_]{1,15}$/;
const IG_HANDLE = /^[A-Za-z0-9_.]{1,30}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

export const xUrl = (handle) => `https://x.com/${handle}`;
export const instagramUrl = (handle) => `https://www.instagram.com/${handle}/`;

/** 出どころのURLが、その事務所の公式サイト（https）の中か。「https://www.t-powers.co.jp.evil/」のような形は通さない */
function fromAgency(source, agency) {
  const s = String(source ?? '');
  return s.startsWith(agency.url) && !/[\s"'<>\\]/.test(s);
}

/**
 * agencies.json → { updated, rows: [{ name, id, key, agency, agencyUrl, x, instagram, source, seen }], byName: Map(FANZAの名前 → 行) }。
 * 形が違う行・知らない事務所・出どころが事務所のサイトでない行は捨てる。アカウント名の形が違えば、そのSNSだけ捨てる。
 * 同じ名前が2行あれば、どちらの人か決められないので、どちらも使わない
 */
export function normalizeAgencies(raw) {
  const ok = raw && typeof raw === 'object' && !Array.isArray(raw);
  const rows = [];
  for (const r of ok && Array.isArray(raw.rows) ? raw.rows : []) {
    if (!r || typeof r !== 'object') continue;
    const agency = Object.prototype.hasOwnProperty.call(AGENCIES, r.agency) ? AGENCIES[r.agency] : null;
    const name = typeof r.name === 'string' ? r.name.trim() : '';
    if (!agency || !name || !fromAgency(r.source, agency) || !DAY.test(String(r.seen ?? ''))) continue;
    rows.push({
      name,
      id: /^\d{1,12}$/.test(String(r.id ?? '')) ? String(r.id) : '',
      key: r.agency,
      agency: agency.name,
      agencyUrl: agency.url,
      x: X_HANDLE.test(String(r.x ?? '')) ? r.x : '',
      instagram: IG_HANDLE.test(String(r.instagram ?? '')) ? r.instagram : '',
      source: r.source,
      seen: r.seen,
    });
  }
  const count = new Map();
  for (const r of rows) count.set(r.name, (count.get(r.name) ?? 0) + 1);
  const unique = rows.filter((r) => count.get(r.name) === 1);
  return {
    updated: ok && DAY.test(String(raw.updated ?? '')) ? raw.updated : '',
    rows: unique,
    byName: new Map(unique.map((r) => [r.name, r])),
  };
}

/**
 * 女優検索の索引に、所属事務所を足す（行の g に事務所のキー、索引の agencies に {キー: 名前}）。
 * FANZA の id が分かっている行は id で、分からない行は名前で（索引に同じ名前の人が2人以上いれば、付けない）
 */
export function withAgencies(index, agencies) {
  const byNameCount = new Map();
  for (const row of index.actresses) byNameCount.set(row.n, (byNameCount.get(row.n) ?? 0) + 1);
  const actresses = index.actresses.map((row) => {
    const a = agencies.byName.get(row.n);
    if (!a) return row;
    if (a.id ? String(row.id ?? '') !== a.id : byNameCount.get(row.n) !== 1) return row;
    return { ...row, g: a.key };
  });
  const used = new Set(actresses.map((r) => r.g).filter(Boolean));
  const names = Object.fromEntries(Object.entries(AGENCIES).filter(([k]) => used.has(k)).map(([k, v]) => [k, v.name]));
  return { ...index, agencies: names, actresses };
}

/** 事務所ごとの人数（女優検索の「所属事務所」の選択肢に添える）→ [{ key, name, count }]（人数の多い順） */
export function agencyCounts(index) {
  const counts = new Map();
  for (const row of index.actresses) if (row.g) counts.set(row.g, (counts.get(row.g) ?? 0) + 1);
  return [...counts]
    .map(([key, count]) => ({ key, name: AGENCIES[key]?.name ?? key, count }))
    .sort((a, b) => b.count - a.count || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}
