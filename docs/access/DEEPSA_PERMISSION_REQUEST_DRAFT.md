# Draft: permission request to the DeepSA authors

Status: DRAFT, not sent. Review, fill in the bracketed fields, and send it yourself.
Recipient: the corresponding author listed on the DeepSA paper (the address is in the PDF's author
information), or as an issue on https://github.com/newfyu/DeepSA if no address is listed.

---

**Subject:** Permission to use the DeepSA code and checkpoints in a non-commercial research prototype

Dear DeepSA authors,

I am [your name], [role] at [institution or "an independent researcher"]. I am building MedTwin, a
non-commercial research prototype that runs medical-image models locally and reports their outputs
next to the source evidence, with an out-of-distribution check before any model result is shown.
It is not a medical device and is not used for patient care.

I would like to evaluate DeepSA ("Pretrained Subtraction and Segmentation Model for Coronary
Angiograms", https://github.com/newfyu/DeepSA) as the coronary-vessel segmentation step for
X-ray angiograms. The repository does not include a licence file, so I do not have permission to
use the code or the three released checkpoints, and I have not run them.

Could you tell me:

1. Whether I may use the DeepSA code and the released checkpoints for non-commercial research, and
   under which licence (for example MIT, Apache-2.0 or a research-only licence). Adding a LICENSE
   file to the repository would answer this for other users as well.
2. Whether the LM-CAD and FS-CAD datasets linked from the README may be used for research
   evaluation, and under what terms.
3. How you would like the work cited.

What I would do with permission:

- Run the checkpoints locally only. I would not redistribute the weights or the datasets, and I
  would not offer DeepSA as a hosted service.
- Reproduce your reported validation results on the public split before using the model, and
  report my numbers separately from yours, labelled as my reproduction.
- Credit DeepSA and cite your paper wherever its output is shown.

Thank you for releasing this work. I am happy to share the reproduction results with you.

Kind regards,
[your name]
[institution, if any]
[contact address]

---

Notes before sending:

- Nothing in this draft describes any patient or case. Keep it that way.
- The reproduction step matches the integration rule in
  `docs/integration/IEEE_TRACEABILITY.md` section 6. The authors' reported numbers stay
  author-reported until the reproduction is done.
- When a reply arrives, record the licence (or the written permission and its date) in
  `docs/research/RESEARCH_CAPABILITY_BLOCKERS.md`, in the DeepSA row.
