// frontend/src/pages/office/materials.js
// Shared color + material palettes for the furniture and worker figures.
import * as THREE from 'three'

export const toColor = (hex) => new THREE.Color(hex)
// ── Material palette ──────────────────────────────────────────────────────────
export const M = {
  panel:   '#2c2c36',
  panelHi: '#383844',
  fabric:  '#3a3a48',
  desk:    '#4a4a58',
  deskHi:  '#55556a',
  laminate:'#3e3e4a',
  metal:   '#343440',
  metalHi: '#4a4a58',
  black:   '#181820',
  trim:    '#1f1f26',
}

// Per-worker variation (skin + hair) so the office looks like real people.
export const SKINS = ['#e8b98a', '#c98d5f', '#9c6b4a', '#f0c8a0', '#8d5a3a', '#d9a06a']
export const HAIRS = ['#1c1c22', '#3a2c22', '#14141a', '#4a3827', '#2b2b33', '#2f241b']
