/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Pure layout rules: which groups fold into the overflow menu, and which
// access keys the bar's tabs and controls get.

/**
 * Ids of the groups that fold into the overflow ("More") menu.
 *
 * `groups` are in display order: {id, width, priority}. Groups fold lowest
 * priority first and, among equal priorities, rightmost first, until the
 * remaining groups plus the overflow button fit in `available`. Nothing
 * folds when everything fits without the button.
 */
export function foldGroups(available, groups, overflowButtonWidth=40) {
  const total = groups.reduce((sum, group) => sum + group.width, 0);
  if(total <= available) return new Set();
  const order = groups.map((group, index) => ({...group, index}))
    .sort((left, right) => (left.priority ?? 0) - (right.priority ?? 0) ||
      right.index - left.index);
  const folded = new Set();
  let remaining = total;
  for(const group of order) {
    if(remaining + overflowButtonWidth <= available) break;
    folded.add(group.id);
    remaining -= group.width;
  }
  return folded;
}

const KEY = /^[A-Z0-9]{1,3}$/;

function letters(label) {
  return [...String(label ?? '').normalize('NFKD').toUpperCase()]
    .filter((char) => /[A-Z0-9]/.test(char));
}

/**
 * Access keys for a set of items ({id, label, accessKey?}) shown together.
 * Declared keys win; others get the first free letter of their label, then
 * the first free two-letter combination. Returns a Map id -> key.
 */
export function assignAccessKeys(items, reserved=[]) {
  const used = new Set(reserved.map((key) => key.toUpperCase()));
  const keys = new Map();
  for(const item of items) {
    const declared = String(item.accessKey ?? '').toUpperCase();
    if(KEY.test(declared) && !used.has(declared)) {
      keys.set(item.id, declared);
      used.add(declared);
    }
  }
  // A key that is a prefix of another makes the longer one unreachable.
  const free = (key) => !used.has(key) &&
    ![...used].some((other) => other.startsWith(key) || key.startsWith(other));
  for(const item of items) {
    if(keys.has(item.id)) continue;
    const chars = letters(item.label);
    let key = chars.find((char) => free(char));
    if(!key) {
      // Two letters: one from the label first, then any unused first letter
      // (from the end of the alphabet, as Office-style bars do).
      const seconds = [...'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'];
      for(const first of [...chars, ...'ZYXWVUTSRQPONMLKJIHGFEDCBA']) {
        key = seconds.map((second) => first + second).find(free);
        if(key) break;
      }
    }
    if(key) {
      keys.set(item.id, key);
      used.add(key);
    }
  }
  return keys;
}

/**
 * What the typed access-key prefix selects: the item whose key it equals
 * (`match`), or the ids still reachable by typing more (`candidates`).
 */
export function matchAccessKey(keys, typed) {
  const prefix = typed.toUpperCase();
  let match = null;
  const candidates = [];
  for(const [id, key] of keys) {
    if(key === prefix) match = id;
    else if(key.startsWith(prefix)) candidates.push(id);
  }
  return {match, candidates};
}
