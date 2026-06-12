export interface GitCommit {
  hash: string;
  short_hash: string;
  subject: string;
  author_name: string;
  author_email: string;
  date_iso: string;
  date_relative: string;
  refs: string[];
  parents: string[];
}

export interface GraphNode extends GitCommit {
  track: number;
  color: string;
  routes: { fromTrack: number; toTrack: number; color: string }[];
}

const PALETTE = ["#e06c75", "#98c379", "#e5c07b", "#61afef", "#c678dd", "#56b6c2"];

export function computeGitGraph(commits: GitCommit[]): GraphNode[] {
  let activeTracks: (string | null)[] = [];
  const nodes: GraphNode[] = [];

  for (const commit of commits) {
    let track = activeTracks.indexOf(commit.hash);
    if (track === -1) {
      track = activeTracks.findIndex(t => t === null);
      if (track === -1) track = activeTracks.length;
      activeTracks[track] = commit.hash;
    }

    const color = PALETTE[track % PALETTE.length];

    // Snapshot of tracks before we process parents
    const snapshot = [...activeTracks];

    // Consume parents
    if (commit.parents.length > 0) {
      activeTracks[track] = commit.parents[0];
      for (let i = 1; i < commit.parents.length; i++) {
        const p = commit.parents[i];
        if (activeTracks.indexOf(p) === -1) {
          let emptyIdx = activeTracks.findIndex(t => t === null);
          if (emptyIdx === -1) emptyIdx = activeTracks.length;
          activeTracks[emptyIdx] = p;
        }
      }
    } else {
      activeTracks[track] = null;
    }

    // Now figure out routes from 'snapshot' to 'activeTracks'
    // To draw lines down to the next row
    const routes = [];
    for (let i = 0; i < snapshot.length; i++) {
      if (!snapshot[i]) continue;
      const targetHash = snapshot[i];
      // Where did this hash go in the new activeTracks?
      let nextTrack = activeTracks.indexOf(targetHash!);
      if (nextTrack !== -1) {
         routes.push({ fromTrack: i, toTrack: nextTrack, color: PALETTE[nextTrack % PALETTE.length] });
      } else {
         // If a parent was just mapped but it isn't in activeTracks anymore?
         // Actually, if it's the commit we just processed, its parents are in activeTracks.
         // If it's a pass-through track, it stays the same.
         // We handle merges and splits by looking at how the tracks changed.
      }
    }

    // But wait, the lines drawn from THIS commit down to its parents:
    // we need a route from `track` to each parent's track in `activeTracks`
    for (let p of commit.parents) {
      const pTrack = activeTracks.indexOf(p);
      if (pTrack !== -1) {
        routes.push({ fromTrack: track, toTrack: pTrack, color: PALETTE[pTrack % PALETTE.length] });
      }
    }

    // De-duplicate routes
    const uniqueRoutes = Array.from(new Set(routes.map(r => JSON.stringify(r)))).map(s => JSON.parse(s));

    nodes.push({
      ...commit,
      track,
      color,
      routes: uniqueRoutes
    });
  }

  return nodes;
}
