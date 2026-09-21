// Consecutive rows that say the same thing, folded into one.
//
// Memo Studio's history listed "Conclusion Selected" five times in a row and
// "Cards Reordered" three times, which pushed everything else out of a panel
// that shows eight rows. A run keeps its first row (the newest, in a list
// sorted newest-first), its last row, and how many it stands for.
export function collapseRuns(rows, keyOf) {
  const runs = [];
  for (const row of rows || []) {
    const key = keyOf(row);
    const last = runs[runs.length - 1];
    if (last && last.key === key) {
      last.last = row;
      last.count += 1;
    } else {
      runs.push({ key, first: row, last: row, count: 1 });
    }
  }
  return runs;
}
