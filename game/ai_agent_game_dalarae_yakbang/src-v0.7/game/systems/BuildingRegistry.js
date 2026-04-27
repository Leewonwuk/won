import {
  TILE_MOXA, TILE_HAEWOSO, TILE_ACU, TILE_HERB,
  TILE_WELL, TILE_GUKBAP, TILE_PINE
} from './GridSystem.js';
import { BALANCE } from '../config.js';

// ─── 건물 메타 단일 출처 ─────────────────────────────────
// GridSystem·PathSystem·GameScene·UI 가 모두 이 객체를 참조한다.
// 신규 건물 추가 시 여기에만 추가하면 됨.
export const BUILDINGS = {
  moxa: {
    key: 'moxa',
    label: '뜸방',
    tileType: TILE_MOXA,
    category: 'treat',
    cost: BALANCE.costs.moxa,
    fee: BALANCE.fees.moxa,
    useMs: BALANCE.treatUseMs,
    myeonguiOnUse: BALANCE.myeonguiOnUse.moxa,
    myeonguiOnSatisfy: BALANCE.myeonguiOnSatisfy.moxa,
    texture: 'tex_building_moxa',
    walkable: false
  },
  acu: {
    key: 'acu',
    label: '침방',
    tileType: TILE_ACU,
    category: 'treat',
    cost: BALANCE.costs.acu,
    fee: BALANCE.fees.acu,
    useMs: BALANCE.treatUseMs,
    myeonguiOnUse: BALANCE.myeonguiOnUse.acu,
    myeonguiOnSatisfy: BALANCE.myeonguiOnSatisfy.acu,
    texture: 'tex_building_acu',
    walkable: false
  },
  herb: {
    key: 'herb',
    label: '약방',
    tileType: TILE_HERB,
    category: 'treat',
    cost: BALANCE.costs.herb,
    fee: BALANCE.fees.herb,
    useMs: BALANCE.treatUseMs,
    myeonguiOnUse: BALANCE.myeonguiOnUse.herb,
    myeonguiOnSatisfy: BALANCE.myeonguiOnSatisfy.herb,
    texture: 'tex_building_herb',
    walkable: false
  },
  haewoso: {
    key: 'haewoso',
    label: '해우소',
    tileType: TILE_HAEWOSO,
    category: 'amenity',
    cost: BALANCE.costs.haewoso,
    fee: BALANCE.fees.haewoso,
    useMs: BALANCE.amenityUseMs,
    stayBonusMs: BALANCE.stayBonusHaewosoMs,
    myeonguiOnUse: 0,
    myeonguiOnSatisfy: 0,
    texture: 'tex_building_haewoso',
    walkable: false
  },
  gukbap: {
    key: 'gukbap',
    label: '국밥집',
    tileType: TILE_GUKBAP,
    category: 'amenity',
    cost: BALANCE.costs.gukbap,
    fee: BALANCE.fees.gukbap,
    useMs: BALANCE.gukbapUseMs,
    stayBonusMs: BALANCE.stayBonusGukbapMs,
    myeonguiOnUse: 0,
    myeonguiOnSatisfy: 0,
    texture: 'tex_building_gukbap',
    walkable: false
  },
  well: {
    key: 'well',
    label: '우물',
    tileType: TILE_WELL,
    category: 'amenity',
    cost: BALANCE.costs.well,
    fee: 0,
    useMs: BALANCE.amenityUseMs,
    stayBonusMs: BALANCE.stayBonusWellMs,
    myeonguiOnUse: 0,
    myeonguiOnSatisfy: 0,
    texture: 'tex_building_well',
    walkable: false
  },
  pine: {
    key: 'pine',
    label: '소나무',
    tileType: TILE_PINE,
    category: 'decor',
    cost: BALANCE.costs.pine,
    fee: 0,
    myeonguiOnUse: 0,
    myeonguiOnSatisfy: 0,
    texture: 'tex_building_pine',
    walkable: false
  }
};

// ─── 조회 헬퍼 ─────────────────────────────────────────
export function getBuildingByKey(key) {
  return BUILDINGS[key] || null;
}

export function getBuildingByTileType(tileType) {
  for (const b of Object.values(BUILDINGS)) {
    if (b.tileType === tileType) return b;
  }
  return null;
}

export function listBuildingsByCategory(category) {
  return Object.values(BUILDINGS).filter((b) => b.category === category);
}

export function isBuildingTileType(tileType) {
  return getBuildingByTileType(tileType) !== null;
}
