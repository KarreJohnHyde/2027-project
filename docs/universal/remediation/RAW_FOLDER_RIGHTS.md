# Rights and integrity of the six raw dataset folders (14 November 2026)

**Method:** the local folders were inspected for licence, readme and metadata files, and quoted terms were read as source evidence. None of these folders is prepared, registered or trained. All six stay **blocked for training** until a publisher licence is recorded. The owner's research-purpose decision does not supply a missing licence, and nothing here implies commercial permission.

| Folder (local) | Size | Licence evidence in the folder | Recorded terms | Training status | Integrity risks |
|---|---|---|---|---|---|
| `Dataset_BUSI_with_GT` (breast ultrasound, Al-Dhabyani et al. 2020) | 1,578 files, 254 MB | None | Not recorded locally. A licence claimed on a mirror is not publisher evidence. | **BLOCKED**: record the publisher's terms first | Several images per patient, with no patient IDs: patient separation cannot be verified |
| `COVID-19_Radiography_Dataset` | 42,335 files, 769 MB | `README.md.txt`: cite two articles; "researchers can use this database to produce useful and impactful scholarly work" | Research and scholarly use with citation is indicated. No licence is stated. Images are compiled from several upstream sources with their own terms. | **BLOCKED** until upstream terms are recorded per source | Upstream sources overlap other public chest X-ray sets; cross-dataset duplicates are likely |
| `TB_Chest_Radiography_Database` | 4,203 files, 662 MB | `README.md.txt`: part of the data is restricted, and users are directed to the NIAID portal to sign a data-sharing agreement | NIAID portion requires a signed agreement | **BLOCKED**: needs the owner's signed NIAID agreement, or exclusion of that portion | Includes the Shenzhen and Montgomery images **already used** in `nlm-tb-cxr`: training or testing on both would leak |
| `lung_colon_image_set` (LC25000 histology) | 25,000 files, 1.8 GB | None | Not recorded locally | **BLOCKED**: record the publisher's terms | The 25,000 images are augmentations of 1,250 originals, so any random split leaks. Augmentation groups would be needed first. |
| `bone_marrow_cell_dataset` (bone-marrow cytomorphology) | 171,374 files, 6.6 GB | None | Not recorded locally; must be confirmed on the publisher's page | **BLOCKED** until confirmed | Patient IDs are not in the folder structure |
| `subset0` to `subset4` (LUNA16, 5 of 10 subsets) | 890 files, 57.2 GB | None | LUNA16 derives from LIDC-IDRI; challenge terms not recorded locally | **BLOCKED**: record the terms | Scans overlap LIDC-IDRI patients **already used** in `lidc-nodule-segmentation`: test patients could leak |

## Next actions

**Owner:**
1. Supply each publisher's licence page, or a signed agreement (NIAID).
2. Decide whether the overlapping sets (TB Chest Radiography, LUNA16) add value beyond the sets already in use.

**Engineering (after terms are recorded):**
- Register each dataset with its evidence.
- Build patient or augmentation groups.
- Cross-check SHA-256 and series UIDs against `nlm-tb-cxr` and `lidc-idri-subset` before any split.
