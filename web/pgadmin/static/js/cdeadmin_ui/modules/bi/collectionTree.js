/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure helpers over the nested collection tree returned by
 * bi_collection_list ([{collection_id, parent_id, name, description,
 * children: [...]}]) and the flat question summaries from bi_question_list.
 */

import {accessOf, rank} from './sharing';

/** The "Shared with me" entry of the collection list (a selection value, never a collection id). */
export const SHARED_ROOT = '__shared__';

/** True when `selected` names a real collection (not the all / none / shared selections). */
export const isCollectionId = (selected) => typeof selected === 'string' && selected !== SHARED_ROOT;

/** Items the caller owns (a backend that predates sharing sends no is_owner: all of them). */
export const ownedItems = (items) => items.filter((item) => item.is_owner !== false);

/** Items other people shared with the caller. */
export const sharedItems = (items) => items.filter((item) => item.is_owner === false);

/**
 * Collections an item may be filed in: the caller's own plus shared ones the
 * caller can edit, those labelled under `sharedLabel`.
 */
export function placementRows(tree, sharedTree, sharedLabel) {
  const shared = flattenCollections(sharedTree)
    .filter((row) => rank(accessOf(row.collection)) >= rank('edit'))
    .map((row) => ({...row, path: [sharedLabel, ...row.path]}));
  return [...flattenCollections(tree), ...shared];
}

/** Depth-first rows [{id, name, parentId, depth, path, collection}]. */
export function flattenCollections(tree, depth = 0, parentPath = []) {
  const rows = [];
  for(const node of tree || []) {
    const path = [...parentPath, node.name];
    rows.push({id: node.collection_id, name: node.name, parentId: node.parent_id ?? null,
      depth, path, collection: node});
    rows.push(...flattenCollections(node.children, depth + 1, path));
  }
  return rows;
}

function find(tree, id) {
  for(const node of tree || []) {
    if(node.collection_id === id) return node;
    const inner = find(node.children, id);
    if(inner) return inner;
  }
  return null;
}

export const findCollection = find;

/** A collection in either tree (own or shared). */
export const findAnyCollection = (tree, sharedTree, id) => find(tree, id) || find(sharedTree, id);

/** Ids of a collection and everything below it. */
export function subtreeIds(tree, id) {
  const node = find(tree, id);
  if(!node) return [];
  return flattenCollections([node]).map((row) => row.id);
}

/** Collections a collection may move under: not itself, not a descendant. */
export function moveTargets(tree, id) {
  const blocked = new Set(subtreeIds(tree, id));
  return flattenCollections(tree).filter((row) => !blocked.has(row.id));
}

export function collectionPath(tree, id) {
  if(id === null || id === undefined) return [];
  return flattenCollections(tree).find((row) => row.id === id)?.path || [];
}

/** Question counts per collection id; the key `null` counts the root. */
export function questionCounts(questions) {
  const counts = new Map();
  for(const question of questions) {
    const key = question.collection_id ?? null;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

/**
 * Questions to list. `collectionId` undefined means every collection; null
 * means the root only. Search matches the name, case-insensitively.
 */
export function visibleQuestions(questions, {collectionId, text = '', includeArchived = false} = {}) {
  const needle = text.trim().toLowerCase();
  return questions.filter((question) => {
    if(!includeArchived && question.status === 'archived') return false;
    if(collectionId !== undefined && (question.collection_id ?? null) !== collectionId) return false;
    return !needle || question.name.toLowerCase().includes(needle);
  });
}

/** Collections whose own name matches, plus their ancestors (for search). */
export function matchingCollectionIds(tree, text) {
  const needle = text.trim().toLowerCase();
  if(!needle) return null;
  const keep = new Set();
  const walk = (nodes, trail) => {
    for(const node of nodes || []) {
      const here = [...trail, node.collection_id];
      if(node.name.toLowerCase().includes(needle)) here.forEach((id) => keep.add(id));
      walk(node.children, here);
    }
  };
  walk(tree, []);
  return keep;
}
