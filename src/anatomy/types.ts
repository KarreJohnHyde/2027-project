export type TierName = "standard" | "preview";

export type AnatomyTier = {
  url: string;
  bytes: number;
  sha256: string;
  triangles: number;
  points: number;
  triangle_ratio_vs_source: number | null;
  bounds_relative_deviation: number | null;
  geometry_changed: boolean;
  transforms: string[];
};

export type StructureEntry = {
  id: string;
  source_key: string;
  label: string;
  label_source: "SOURCE_NAME" | "CURATED_TRANSLATION" | "CURATED_EXPANSION" | "CURATED_INFERENCE" | "NONE";
  note: string | null;
  review_status: string;
  nodes: string[];
  triangles: number;
};

export type LicenseInfo = { id: string; class: string; commercial_use: boolean; share_alike: boolean; redistribution: string };

export type Alignment = {
  method: string;
  extent_difference_before_mm: number[];
  translation_m: number[];
  residual_after_translation_mm: number[];
  status: string;
  caveat: string;
};

export type AnatomyVariant = {
  id: string;
  system_id: string;
  kind: "STANDALONE_ASSET" | "ATLAS_REFERENCE";
  label: string;
  role: string;
  view_types: string[];
  available: boolean;
  default_tier: TierName;
  tiers?: Partial<Record<TierName, AnatomyTier>>;
  atlas?: { chunks: string[]; groups: string[]; structure_count: number };
  source: {
    relative_path: string;
    sha256?: string;
    bytes?: number;
    title: string | null;
    author: string | null;
    source_url: string | null;
    license_text: string | null;
    generator?: string | null;
    validator?: { status: string; errors: number; issue_codes: Record<string, number> };
    content_hash?: string;
  };
  license: LicenseInfo;
  statistics: Record<string, unknown>;
  structures?: StructureEntry[];
  group_by?: "material" | "parent" | "node";
  labelled_structures: number;
  frame: string;
  registration: { status: string; representation_level: string; reference_frame?: string; alignment?: Alignment };
  notes: string[];
  repairs?: string[];
};

export type ComparisonTransform = {
  method: string;
  scale: number;
  translation: number[];
  residual_width_mm: number;
  residual_depth_mm: number;
  status: string;
  caveat: string;
};

export type HybridLayer = {
  id: string;
  label: string;
  kind: "ATLAS_LAYER" | "ASSET_LAYER" | "UNREGISTERED_COMPARISON";
  default_on: boolean;
  registration: string;
  atlas_systems?: string[];
  atlas_groups?: string[];
  exclude_groups?: string[];
  chunks?: string[];
  structure_count?: number;
  variant_id?: string;
  translation_m?: number[];
  alignment?: Alignment;
  transform?: ComparisonTransform;
};

export type AnatomySystem = {
  id: string;
  order: number;
  label: string;
  specialty: string;
  summary: string;
  variants: string[];
  default_variant: string;
  hybrid: { frame: Record<string, string>; body_bounds: { min: number[]; max: number[] }; layers: HybridLayer[]; review_workflow: string } | null;
  limitations: string[];
};

export type AnatomyManifest = {
  schema_version: string;
  generated_at_utc: string;
  curation: { curated_by: string; curated_on: string; review_status: string };
  representation_level: string;
  notice: string;
  mapping_categories: Record<string, string>;
  atlas_index_url: string;
  atlas_attribution_url: string;
  totals: { systems: number; variants: number; available_variants: number; derived_bytes: number; atlas_structures: number };
  systems: AnatomySystem[];
  variants: Record<string, AnatomyVariant>;
  excluded: Array<{ source?: string; source_prefix?: string; reason: string; detail: string }>;
};

export type AtlasStructure = {
  id: string;
  parent: string | null;
  system: string;
  kind: "structure" | "group" | "system";
  side: string | null;
  meshes: number[];
  name: string;
  name_la: string | null;
  review: string;
};

export type AtlasChunk = {
  id: string;
  system: string;
  mesh_start: number;
  mesh_count: number;
  standard: { url: string; bytes: number; sha256: string; triangles: number };
  economy: { url: string; bytes: number; sha256: string; triangles: number };
};

export type AtlasIndex = {
  schema_version: string;
  release: { version: string; channel: string; content_hash: string; generated_at: string };
  coordinates: { up: string; front: string; units: string; origin: string };
  bounds: { min: number[]; max: number[] };
  notices: { review: string; data: string };
  palette: string[];
  palette_kinds: string[];
  issues: Array<{ id: string; kind: string; text: string; status: string }>;
  assets: Array<{ id: string; title: string; authors: string[]; license: { id: string; name: string; url: string }; source: { name: string; url?: string } }>;
  systems: string[];
  chunks: AtlasChunk[];
  structures: AtlasStructure[];
};

/** A structure selected in the viewport, independent of the layer type. */
export type StructureRef = { layer: string; id: string; label: string; source: "ASSET" | "ATLAS" };
