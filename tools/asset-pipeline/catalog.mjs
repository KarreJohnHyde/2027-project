// Curated assignment of inspected anatomy assets to the ten MedTwin workspaces.
//
// Everything here is curator metadata layered on top of the automated
// inventory (docs/anatomy/inventory). Labels carry an explicit provenance:
//   SOURCE_NAME          the asset's own node/material name, humanised
//   CURATED_TRANSLATION  a non-English source name translated by the curator
//   CURATED_EXPANSION    an abbreviation expanded by the curator
//   CURATED_INFERENCE    inferred from a non-anatomical name (lower confidence)
// No label below has had independent anatomical review.

export const CURATION = {
  curated_by: "MedTwin asset curation (automated inspection + curator notes)",
  curated_on: "2026-10-24",
  review_status: "CURATOR_PROPOSED_UNREVIEWED",
};

/** License classes drive the deployment notices shown in the UI. */
export function classifyLicense(raw) {
  const text = String(raw ?? "").toUpperCase();
  if (!text || text === "NONE" || text === "NULL") {
    return { id: "UNKNOWN", class: "UNKNOWN", commercial_use: false, share_alike: false, redistribution: "BLOCKED_PENDING_LICENSE" };
  }
  if (text.includes("SKETCHFAB STANDARD")) {
    return {
      id: "SKETCHFAB-STANDARD",
      class: "RESTRICTED",
      commercial_use: true,
      share_alike: false,
      redistribution: "LOCAL_RESEARCH_ONLY_NO_STANDALONE_REDISTRIBUTION",
    };
  }
  const id = (text.match(/CC-BY(?:-NC)?(?:-SA)?(?:-ND)?-\d\.\d/) ?? [text.split(" ")[0]])[0];
  const nonCommercial = id.includes("-NC");
  const shareAlike = id.includes("-SA");
  return {
    id,
    class: nonCommercial ? "NON_COMMERCIAL" : shareAlike ? "SHARE_ALIKE" : "ATTRIBUTION",
    commercial_use: !nonCommercial,
    share_alike: shareAlike,
    redistribution: nonCommercial ? "NON_COMMERCIAL_WITH_ATTRIBUTION" : shareAlike ? "ATTRIBUTION_SHARE_ALIKE" : "ATTRIBUTION",
  };
}

// Atlas group ids (Z-Anatomy-derived release 1.2.0) used for in-body references.
export const ATLAS_SELECTIONS = {
  heart: { chunks: ["cardiovascular.arterial_system"], groups: ["cardiovascular.heart"] },
  lungs: { chunks: ["visceral.endocrine_glands--respiratory_system"], groups: ["visceral.respiratory_system"] },
  brain: {
    chunks: ["nervous.brain", "nervous.telencephalon", "nervous.telencephalon.2", "nervous.white_matter_of_telencephalon_l"],
    groups: ["nervous.brain"],
  },
  liver: { chunks: ["visceral.digestive_system"], groups: ["visceral.liver", "visceral.gallbladder", "visceral.bile_duct"], include_structures: true },
  pancreas: { chunks: ["visceral.digestive_system"], groups: ["visceral.pancreas"], include_structures: true },
  intestines: { chunks: ["visceral.digestive_system"], groups: ["visceral.small_intestine", "visceral.large_intestine"] },
  nervous: {
    chunks: [
      "nervous.central_nervous_system",
      "nervous.spinal_cord--autonomic_division_of_peripheral_nervous",
      "nervous.peripheral_nervous_system",
      "nervous.spinal_nerves",
      "nervous.brain",
    ],
    groups: ["nervous"],
  },
  skeletal: {
    chunks: [
      "skeletal.cranium--extracranial_bones_of_head",
      "skeletal.vertebral_column",
      "skeletal.thoracic_skeleton",
      "skeletal.bones_of_upper_limb",
      "skeletal.auditory_ossicles--bones_of_lower_limb",
      "skeletal.laryngeal_cartilages--teeth",
    ],
    groups: ["skeletal"],
  },
  kidneys: { chunks: ["visceral.urinary_system"], groups: ["visceral.urinary_system"] },
};

// Hybrid full-body layers. Every atlas layer shares the Z-Anatomy frame
// (+Y up, +Z front, metres, origin on the floor between the heels).
export const HYBRID_LAYERS = [
  { id: "skeleton", label: "Skeleton", atlas_systems: ["skeletal"], default_on: true },
  { id: "joints", label: "Joints and ligaments", atlas_systems: ["joints"], default_on: false },
  { id: "muscles", label: "Muscles", atlas_systems: ["muscular", "insertions"], default_on: false },
  { id: "vascular", label: "Vascular system", atlas_systems: ["cardiovascular"], exclude_groups: ["cardiovascular.heart"], default_on: false },
  { id: "nervous", label: "Nervous system", atlas_systems: ["nervous"], exclude_groups: ["nervous.brain"], default_on: false },
  { id: "heart", label: "Heart", atlas_groups: ["cardiovascular.heart"], default_on: true },
  { id: "lungs", label: "Lungs and airways", atlas_groups: ["visceral.respiratory_system"], default_on: true },
  { id: "brain", label: "Brain", atlas_groups: ["nervous.brain"], default_on: true },
  { id: "liver", label: "Liver and biliary tree", atlas_groups: ["visceral.liver", "visceral.gallbladder", "visceral.bile_duct"], default_on: true },
  { id: "pancreas", label: "Pancreas", atlas_groups: ["visceral.pancreas"], default_on: true },
  { id: "intestines", label: "Stomach and intestines", atlas_groups: ["visceral.digestive_canal"], default_on: true },
  { id: "kidneys", label: "Kidneys and urinary tract", atlas_groups: ["visceral.urinary_system"], default_on: true },
  { id: "lymphoid", label: "Lymphoid system", atlas_systems: ["lymphoid"], default_on: false },
  { id: "skin", label: "Body regions (surface)", atlas_systems: ["regions"], default_on: false },
];

const HEART_LABELS = {
  new_med_high_res_model: { label: "Heart (myocardium and chambers, cut-away interior)", label_source: "CURATED_INFERENCE" },
  med_detail_int: { label: "Interior detail surface", label_source: "CURATED_INFERENCE" },
  main_body2: { label: "Heart (external surface)", label_source: "CURATED_INFERENCE" },
  coronary_sinus_and_great_cardiac_vein: { label: "Coronary sinus and great cardiac vein", label_source: "SOURCE_NAME" },
  posterior_vein_of_left_ventricle: { label: "Posterior vein of left ventricle", label_source: "SOURCE_NAME" },
  posterior_vein_of_left_ventricle_2: { label: "Posterior vein of left ventricle (second segment)", label_source: "SOURCE_NAME" },
  cercumflex_branch_of_left_coronary_artery: {
    label: "Circumflex branch of left coronary artery",
    label_source: "SOURCE_NAME",
    note: "Source spells 'cercumflex'.",
  },
  small_cardiac_vein: { label: "Small cardiac vein", label_source: "SOURCE_NAME" },
  middle_cardiac_vein: { label: "Middle cardiac vein", label_source: "SOURCE_NAME" },
  right_coronary_artery: { label: "Right coronary artery", label_source: "SOURCE_NAME" },
  right_coronary_artery_2: { label: "Right coronary artery", label_source: "SOURCE_NAME" },
  right_coronary_artery_3: { label: "Right coronary artery (distal segment)", label_source: "SOURCE_NAME" },
  right_coronary_artery___posterior_interventricular_artery: {
    label: "Right coronary artery / posterior interventricular artery",
    label_source: "SOURCE_NAME",
  },
};

/**
 * Systems, in the order mandated for the Anatomy Studio. Each variant names a
 * workspace-relative source file; build-manifest.mjs joins it with the
 * inventory record for provenance, licence and structure statistics.
 */
export const SYSTEMS = [
  {
    id: "heart",
    order: 1,
    label: "Heart",
    specialty: "Cardiology",
    summary: "External and internal cardiac anatomy from attributed educational models, plus a structure-labelled in-body atlas heart.",
    variants: [
      {
        id: "heart-interior-dundee",
        label: "Interior heart — high detail",
        source: "interior_heart_-_high_detail.glb",
        role: "INTERIOR",
        group_by: "material",
        labels: HEART_LABELS,
        notes: ["Authored as a cut-away interior model; chamber walls are not separately segmented in the source."],
      },
      {
        id: "heart-exterior-dundee",
        label: "Exterior heart — high detail",
        source: "exterior_heart_-_high_detail.glb",
        role: "EXTERIOR",
        group_by: "material",
        labels: HEART_LABELS,
      },
      {
        id: "heart-external-newey",
        label: "Heart — external surface anatomy",
        source: "cardiac_anatomy_external_view_of_human_heart.glb",
        role: "EXTERIOR",
        group_by: "node",
        notes: ["41 source segments carry no anatomical names; they are shown as unlabelled segments."],
      },
    ],
    atlas: true,
    limitations: [
      "Generic reference anatomy; no patient-specific cardiac geometry.",
      "Ejection fraction or chamber volumes are never derived from these models.",
    ],
  },
  {
    id: "lungs",
    order: 2,
    label: "Lungs",
    specialty: "Pulmonology",
    summary: "Lung, airway and bronchial reference models; the atlas variant labels individual lobes and the tracheobronchial tree.",
    variants: [
      {
        id: "lungs-airways-umcg",
        label: "Tracheobronchial tree — airway anatomy",
        source: "anatomy_of_the_airways.glb",
        role: "SUBSTRUCTURE",
        group_by: "parent",
        labels: {
          bronchi1: { label: "Bronchial tree", label_source: "SOURCE_NAME" },
          bronchi1_1: { label: "Bronchial tree (second segment)", label_source: "SOURCE_NAME" },
          Linkerlong: { label: "Left lung", label_source: "CURATED_TRANSLATION", note: "Dutch 'linkerlong'." },
          Trachea_kraakbeen: { label: "Tracheal cartilage", label_source: "CURATED_TRANSLATION", note: "Dutch 'kraakbeen' = cartilage." },
          Tussen_hyoid_en_thyroid: { label: "Thyrohyoid membrane", label_source: "CURATED_TRANSLATION", note: "Dutch 'between hyoid and thyroid'." },
          Hyoid_bone: { label: "Hyoid bone", label_source: "SOURCE_NAME" },
          Thyroid_gland: { label: "Thyroid gland", label_source: "SOURCE_NAME" },
        },
      },
      { id: "lungs-normal-valchanov", label: "Lungs — normal anatomy", source: "lungs_-_normal_study.glb", role: "EXTERIOR", group_by: "node" },
      {
        id: "lungs-realistic-neshallads",
        label: "Lungs — surface anatomy",
        source: "realistic_human_lungs.glb",
        role: "EXTERIOR",
        group_by: "material",
        labels: {
          thairoid01lungh_part01: { label: "Lung surface (part 1)", label_source: "SOURCE_NAME" },
          thairoid01lungh_part02: { label: "Lung surface (part 2)", label_source: "SOURCE_NAME" },
        },
      },
      {
        id: "lungs-transparent-alebogino",
        label: "Lungs — transparent lobes",
        source: "pulmones_con_transparencia.glb",
        role: "TRANSPARENT",
        group_by: "parent",
        labels: {
          "Pulmones RAW.001": { label: "Lung surface (shell 1)", label_source: "CURATED_TRANSLATION", note: "Spanish 'pulmones' = lungs." },
          "Pulmones RAW.002": { label: "Lung surface (shell 2)", label_source: "CURATED_TRANSLATION", note: "Spanish 'pulmones' = lungs." },
        },
        notes: ["Source contains an animation; MedTwin never plays asset animations as physiology."],
      },
      {
        id: "lungs-right-prasanth",
        label: "Right lung, trachea and larynx",
        source: "source/lung_right.glb",
        role: "SUBSTRUCTURE",
        group_by: "parent",
        labels: {
          Respiratoy_Lung_Geo_Right: { label: "Right lung", label_source: "SOURCE_NAME" },
          Respiratoy_Trachea_Geo: { label: "Trachea and bronchi", label_source: "SOURCE_NAME" },
          Respiratory_Cricothyroid_Ligament_Geo: { label: "Cricothyroid ligament", label_source: "SOURCE_NAME" },
          Respiratoy_Epiglotis_Geo: { label: "Epiglottis", label_source: "SOURCE_NAME" },
          Respiratoy_Epiglotis_Inner_Geo: { label: "Epiglottis (inner surface)", label_source: "SOURCE_NAME" },
          Respiratoy_Thyroid_Membrane_Geo: { label: "Thyrohyoid membrane", label_source: "SOURCE_NAME" },
          Respiratoy_Thyroid_Cartliage_Geo: { label: "Thyroid cartilage", label_source: "SOURCE_NAME" },
          Respiratoy_True_Vocal_Fold_Geo_Left: { label: "Left true vocal fold", label_source: "SOURCE_NAME" },
          Respiratoy_True_Vocal_Fold_Geo_Right: { label: "Right true vocal fold", label_source: "SOURCE_NAME" },
        },
        notes: ["Node names reference a 'Male Anatomy Pack'; the uploader's CC-BY declaration has not been independently verified."],
      },
      {
        id: "lungs-carcinoma-holt",
        label: "Lung carcinoma — educational depiction",
        source: "lung_carcinoma.glb",
        role: "PATHOLOGY_DEPICTION",
        group_by: "node",
        notes: ["Educational depiction of a carcinoma. It is never a patient finding and is never linked to case evidence."],
      },
    ],
    atlas: true,
    limitations: ["Generic reference anatomy; lesion overlays require a validated detector and registration, neither of which is configured."],
  },
  {
    id: "brain",
    order: 3,
    label: "Brain",
    specialty: "Neurology",
    summary: "Exterior brain surfaces, a lobe-labelled model and a structure-labelled atlas brain (brainstem, cerebellum, telencephalon).",
    variants: [
      {
        id: "brain-lobes-versal",
        label: "Cerebrum — lobar anatomy",
        source: "human_brain (1).glb",
        role: "SUBSTRUCTURE",
        group_by: "parent",
        labels: {
          brain1: { label: "Brain (unlabelled portion)", label_source: "SOURCE_NAME" },
          cereb1: { label: "Cerebellum", label_source: "CURATED_EXPANSION" },
          frontal1: { label: "Frontal lobe", label_source: "CURATED_EXPANSION" },
          occipit1: { label: "Occipital lobe", label_source: "CURATED_EXPANSION" },
          pariet1: { label: "Parietal lobe", label_source: "CURATED_EXPANSION" },
          temp1: { label: "Temporal lobe", label_source: "CURATED_EXPANSION" },
        },
      },
      { id: "brain-budi", label: "Brain — surface anatomy", source: "brain.glb", role: "EXTERIOR", group_by: "node" },
      { id: "brain-model-kalitkap", label: "Brain — gross anatomy model", source: "brain_model.glb", role: "EXTERIOR", group_by: "node" },
      { id: "brain-3drt", label: "Brain — low-polygon surface", source: "human_brain.glb", role: "EXTERIOR", group_by: "node" },
      {
        id: "brain-point-cloud-terrie",
        label: "Brain — point cloud",
        source: "brain_point_cloud.glb",
        role: "POINT_CLOUD",
        group_by: "node",
        notes: ["Point primitives only: no surfaces, so sectioning and opacity behave differently from meshes."],
      },
      {
        id: "brain-hologram-oxterium",
        label: "Brain — stylised holographic rendering",
        source: "brain_hologram.glb",
        role: "STYLIZED",
        group_by: "node",
        notes: ["Particle-based artwork, not anatomical geometry.", "Source contains an animation that MedTwin does not play."],
      },
    ],
    atlas: true,
    limitations: ["Lesion and tumour overlays require validated stroke/tumour models with matched labels; none is configured."],
  },
  {
    id: "liver",
    order: 4,
    label: "Liver",
    specialty: "Hepatology",
    summary: "Liver surfaces, a vascular graft-planning model, and the atlas liver with Couinaud segments I–VIII.",
    variants: [
      {
        id: "liver-3graft-chloroplast",
        label: "Whole liver with hepatic vasculature",
        source: "3graft_whole_liver.glb",
        role: "SUBSTRUCTURE",
        group_by: "parent",
        label_patterns: [
          { match: /\bHA\b/, label: "Hepatic artery (HA)", label_source: "CURATED_EXPANSION" },
          { match: /\bHV\b/, label: "Hepatic veins (HV)", label_source: "CURATED_EXPANSION" },
          { match: /\bLLS\b/, label: "Left lateral section (LLS)", label_source: "CURATED_EXPANSION" },
          { match: /\bMS\b/, label: "Middle section (MS)", label_source: "CURATED_EXPANSION" },
          { match: /\bPV\b/, label: "Portal vein (PV)", label_source: "CURATED_EXPANSION" },
          { match: /Right lobe/, label: "Right lobe", label_source: "SOURCE_NAME" },
        ],
        notes: ["Source node names contain undecodable non-Latin text; abbreviations were expanded by the curator."],
      },
      { id: "liver-9darsh", label: "Liver — surface anatomy", source: "liver.glb", role: "EXTERIOR", group_by: "node" },
      {
        id: "liver-scan-errinroy",
        label: "Liver — photogrammetry scan of a physical model",
        source: "liver (1).glb",
        role: "EXTERIOR",
        group_by: "node",
        notes: ["Captured with the Qlone scanning app; reproduces a physical teaching model."],
      },
    ],
    atlas: true,
    limitations: ["Fibrosis stage, steatosis or lesion burden are never inferred from a generic liver model."],
  },
  {
    id: "pancreas",
    order: 5,
    label: "Pancreas",
    specialty: "Endocrinology / Gastroenterology",
    summary: "Pancreas surface, an authored cross-section, and the atlas pancreas with main and accessory ducts.",
    variants: [
      { id: "pancreas-captaainro", label: "Pancreas — surface anatomy", source: "pancreas.glb", role: "EXTERIOR", group_by: "node" },
      {
        id: "pancreas-cross-section-arloopa",
        label: "Pancreas — cross-section",
        source: "human_pancreas_cross_section.glb",
        role: "CROSS_SECTION",
        group_by: "node",
      },
    ],
    atlas: true,
    limitations: [
      "Metabolic markers (glucose, HbA1c) are not anatomical pancreatic findings and are never mapped onto pancreatic geometry.",
    ],
  },
  {
    id: "intestines",
    order: 6,
    label: "Intestines",
    specialty: "Gastroenterology",
    summary: "Small and large intestine model plus atlas segments (duodenum, jejunum, colon segments, rectum).",
    variants: [
      {
        id: "intestines-sundberg",
        label: "Small and large intestine",
        source: "small_and_large_intestine.glb",
        role: "EXTERIOR",
        group_by: "parent",
        labels: {
          Tjocktarm: { label: "Large intestine", label_source: "CURATED_TRANSLATION", note: "Swedish 'tjocktarm'." },
          Tunntarm: { label: "Small intestine", label_source: "CURATED_TRANSLATION", note: "Swedish 'tunntarm'." },
        },
      },
    ],
    atlas: true,
    limitations: ["Endoscopic findings have no anatomical coordinates without procedure metadata; they are never placed on this geometry."],
  },
  {
    id: "nervous",
    order: 7,
    label: "Nervous system",
    specialty: "Neurology",
    summary: "Whole-body nervous system layer and the atlas central/peripheral nervous structures in the shared body frame.",
    variants: [
      {
        id: "nervous-zanatomy-neurology",
        label: "Nervous system — whole-body neurological layer",
        source: "neurology.glb",
        role: "LAYERED",
        group_by: "material",
        humanize_material: true,
        frame: "Z_ANATOMY_ADULT_MALE",
        notes: ["Structure labels are the source's tissue-class material names (e.g. Brain, Cerebellum, Nerve)."],
      },
    ],
    atlas: true,
    limitations: ["Nerve pathways absent from the source assets are never drawn or interpolated."],
  },
  {
    id: "skeletal",
    order: 8,
    label: "Skeletal system",
    specialty: "Orthopaedics",
    summary: "Full skeleton with regional bone groups, an écorché muscle study, and the atlas skeleton with individually named bones.",
    variants: [
      {
        id: "skeleton-projectkaizen",
        label: "Adult male skeleton",
        source: "male_skeleton (1).glb",
        role: "LAYERED",
        group_by: "parent",
        labels: {
          ArmsHands: { label: "Upper limb bones (arms and hands)", label_source: "SOURCE_NAME" },
          HipsLegs: { label: "Pelvis and lower limb bones", label_source: "SOURCE_NAME" },
          Sacrum: { label: "Sacrum", label_source: "SOURCE_NAME" },
          HipCartilage: { label: "Hip cartilage", label_source: "SOURCE_NAME" },
          Discs: { label: "Intervertebral discs", label_source: "SOURCE_NAME" },
          Ribs: { label: "Ribs", label_source: "SOURCE_NAME" },
          Sternum: { label: "Sternum", label_source: "SOURCE_NAME" },
          RibCartilage: { label: "Costal cartilage", label_source: "SOURCE_NAME" },
          Spine: { label: "Vertebral column", label_source: "SOURCE_NAME" },
          Hyoid: { label: "Hyoid bone", label_source: "SOURCE_NAME" },
          Cranium: { label: "Cranium", label_source: "SOURCE_NAME" },
          UpperTeeth: { label: "Upper teeth", label_source: "SOURCE_NAME" },
          Mandible: { label: "Mandible", label_source: "SOURCE_NAME" },
          LowerTeeth: { label: "Lower teeth", label_source: "SOURCE_NAME" },
        },
      },
      {
        id: "ecorche-santamaria",
        label: "Écorché — superficial musculature study",
        source: "ecorche_-_anatomy_study.glb",
        role: "ARTISTIC_STUDY",
        group_by: "node",
        notes: ["Sculpted artistic study of superficial musculature; not a dissection-derived model."],
      },
    ],
    atlas: true,
    limitations: ["Fractures or bone lesions are displayed only from a validated detector with registration; none is configured."],
  },
  {
    id: "hybrid",
    order: 9,
    label: "Hybrid full body",
    specialty: "Multi-system",
    summary: "Switchable co-registered layers from one reference atlas frame, with optional unregistered comparison assets.",
    variants: [
      {
        id: "hybrid-angiology-zanatomy",
        label: "Angiology — whole-body vascular layer",
        source: "angiology.glb",
        role: "LAYERED",
        group_by: "material",
        humanize_material: true,
        frame: "Z_ANATOMY_ADULT_MALE",
      },
    ],
    hybrid: true,
    unregistered_comparison: ["skeleton-projectkaizen", "ecorche-santamaria"],
    limitations: [
      "Layers share one reference atlas frame; this is a generic adult male reference body, not the patient's anatomy.",
      "Comparison assets from other sources are scale-aligned by bounding box only and are labelled UNREGISTERED.",
    ],
  },
  {
    id: "kidneys",
    order: 10,
    label: "Kidneys and nephrons",
    specialty: "Nephrology",
    summary: "Kidney exteriors and interiors (cortex, medullary pyramids, capsule, vessels), educational nephron models and the atlas urinary tract.",
    variants: [
      {
        id: "kidney-cgmac",
        label: "Kidney — cortex, pyramids and vessels",
        source: "kidney (1).glb",
        role: "INTERIOR",
        group_by: "parent",
        labels: {
          "Maya_2018:Medulla pyramid": { label: "Medullary pyramids", label_source: "SOURCE_NAME" },
          "Maya_2018:Ureter": { label: "Ureter", label_source: "SOURCE_NAME" },
          "Maya_2018:Cortex": { label: "Renal cortex", label_source: "SOURCE_NAME" },
          "Maya_2018:Capsule": { label: "Renal capsule", label_source: "SOURCE_NAME" },
          "Maya_2018:RED": { label: "Arterial vessels (red in source)", label_source: "CURATED_INFERENCE" },
          "Maya_2018:BLUE": { label: "Venous vessels (blue in source)", label_source: "CURATED_INFERENCE" },
        },
      },
      {
        id: "kidney-payoman",
        label: "Kidney with renal pyramids and vessels",
        source: "kidney.glb",
        role: "INTERIOR",
        group_by: "material",
        labels: {
          Rion: { label: "Kidney (outer surface)", label_source: "CURATED_TRANSLATION", note: "Spanish 'riñón'." },
          kidneyEdge: { label: "Kidney (cut edge)", label_source: "SOURCE_NAME" },
          arterias: { label: "Arteries", label_source: "CURATED_TRANSLATION", note: "Spanish 'arterias'." },
          tronco: { label: "Vascular trunk", label_source: "CURATED_TRANSLATION", note: "Spanish 'tronco'." },
          venas: { label: "Veins", label_source: "CURATED_TRANSLATION", note: "Spanish 'venas'." },
          PiramideRenal: { label: "Renal pyramid", label_source: "CURATED_TRANSLATION", note: "Spanish 'pirámide renal'." },
        },
      },
      { id: "kidney-neshallads", label: "Kidney — surface anatomy", source: "human_kidney.glb", role: "EXTERIOR", group_by: "node" },
      { id: "kidney-safiya", label: "Kidney — gross anatomy", source: "medicine_organ_-_the_human_kidney.glb", role: "EXTERIOR", group_by: "node" },
      { id: "kidney-cowley", label: "Kidney — external surface", source: "kidney (2).glb", role: "INTERIOR", group_by: "node" },
      {
        id: "nephron-iqcenter",
        label: "Nephron — multiscale model",
        source: "nephron.glb",
        role: "MICROANATOMY",
        group_by: "parent",
        labels: {
          Pyramid: { label: "Renal pyramid (context)", label_source: "SOURCE_NAME" },
          nephron_mesher: { label: "Nephron tubule", label_source: "SOURCE_NAME" },
          capillary_artery: { label: "Capillary (arterial side)", label_source: "SOURCE_NAME" },
          capillary_vein: { label: "Capillary (venous side)", label_source: "SOURCE_NAME" },
          cell_right: { label: "Epithelial cells (right)", label_source: "SOURCE_NAME" },
          cell_left: { label: "Epithelial cells (left)", label_source: "SOURCE_NAME" },
          cell_middle: { label: "Epithelial cells (middle)", label_source: "SOURCE_NAME" },
        },
      },
      {
        id: "nephron-aymanba",
        label: "Nephron with blood supply",
        source: "nephron (1).glb",
        role: "MICROANATOMY",
        group_by: "parent",
        labels: {
          Blood_supply: { label: "Blood supply (glomerular and peritubular vessels)", label_source: "SOURCE_NAME" },
          Nephron: { label: "Nephron", label_source: "SOURCE_NAME" },
        },
      },
      {
        id: "nephron-temirbekova",
        label: "Nephron — tubular segments",
        source: "4c183daa67a34efca2480a5862d7ceb0.glb",
        role: "MICROANATOMY",
        group_by: "node",
        notes: ["Identified from the model's embedded metadata (title: Nephron)."],
      },
      { id: "nephron-structure-arloopa", label: "Nephron — structure", source: "structure_of_nephron.glb", role: "MICROANATOMY", group_by: "node" },
    ],
    atlas: true,
    limitations: [
      "Nephron models are educational representations, never patient-specific microanatomy.",
      "eGFR is computed only from a documented creatinine with the inputs a validated equation requires.",
    ],
  },
];

/** Files that were inspected but deliberately not offered in the studio. */
export const EXCLUDED = [
  { source: "public/models/Untitled.glb", reason: "UNATTRIBUTED_REEXPORT", detail: "Blender re-export from 'heart blender/*.blend' without provenance metadata." },
  { source: "public/models/Untitled1.glb", reason: "DUPLICATE_REEXPORT", detail: "Blender re-export of cardiac_anatomy_external_view_of_human_heart.glb (identical triangle count and bounds)." },
  { source: "public/models/Untitled2.glb", reason: "UNATTRIBUTED_REEXPORT", detail: "Blender re-export without provenance metadata." },
  { source: "public/models/Untitled3.glb", reason: "DUPLICATE_REEXPORT", detail: "Blender re-export of exterior_heart_-_high_detail.glb (identical triangle count and bounds)." },
  { source: "source/brain.glb", reason: "DUPLICATE_FORMAT", detail: "Same geometry as brain.glb (19,045 triangles, identical bounds) exported by Microsoft GLTF Exporter." },
  { source: "source/Rotten Brain.glb", reason: "DUPLICATE_FORMAT", detail: "Same geometry as human_brain.glb (4,850 triangles, identical bounds)." },
  { source: "source/model.glb", reason: "DUPLICATE_FORMAT", detail: "pygltflib repack of 4c183daa67a34efca2480a5862d7ceb0.glb (343,273 triangles, identical bounds)." },
  { source_prefix: "anatomy-main/", reason: "LICENSE_UNKNOWN", detail: "Repository has no code licence and no provenance for its nine GLBs." },
  { source_prefix: "public/models/medtwin_l1_", reason: "SUPERSEDED", detail: "Economy-quality atlas chunks from the Phase 1 viewer; superseded by the full atlas release." },
];
