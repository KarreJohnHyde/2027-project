# Draft: PhysioNet credentialing research summary (MIMIC-IV, MIMIC-CXR, VinDr-CXR)

Status: DRAFT, not submitted. You must complete the steps below yourself. PhysioNet credentials
the person, so Claude cannot apply, sign or train on your behalf.

## Steps you take on physionet.org

1. Create or sign in to your PhysioNet account.
2. Complete the CITI course "Data or Specimens Only Research" and upload the completion report.
3. Apply for credentialed access: name a reference (a supervisor or senior colleague who knows
   your research) and paste the research summary below.
4. Once credentialed, sign the data use agreement (the PhysioNet Credentialed Health Data Licence)
   on each project page: MIMIC-IV, MIMIC-CXR (or MIMIC-CXR-JPG) and VinDr-CXR.
5. Check each project page for extra conditions before downloading.

## Research summary (paste into the application)

> I am developing MedTwin, a non-commercial research prototype that runs medical-image and
> clinical-text models on a local workstation and shows their outputs next to the source evidence,
> with an out-of-distribution check that refuses inputs unlike the training data. It is not used
> for patient care.
>
> I am requesting access for three research questions:
>
> 1. VinDr-CXR: train and evaluate a chest-radiograph lesion detector on the radiologist bounding
>    boxes, and measure how often model localisations agree with expert boxes.
> 2. MIMIC-CXR: measure agreement between chest-radiograph model findings and the findings stated
>    in the paired radiology reports.
> 3. MIMIC-IV with MIMIC-CXR: study whether combining images, reports and laboratory values improves
>    prediction of later outcomes over any single source, using repeated measurements per patient.
>
> All data will be stored and processed only on my own workstation and will not be shared,
> redistributed or uploaded. I will not attempt to re-identify any individual. I will not send the
> data, or text derived from it, to online services, including hosted large language models.
> Results will be reported only in aggregate, and any trained model weights will be kept private
> unless the licence allows sharing.

## Things to check before you paste it

- **Your details:** replace "I am developing" with your role and institution if you have one.
  PhysioNet reviews the applicant, not the software.
- **The commitment about AI tools:** it also binds this project's own tooling. Coding agents such
  as Claude Code and Codex may write and run code against the data, but must never be shown the
  records themselves, including file contents, report text, images, row samples or error messages
  quoting them. Keep that rule in `AGENTS.md` if you get access.
- **Storage:** the summary says the data stays on your workstation. If you will store it on a
  shared or cloud drive, change that sentence.
- **Wording:** describe only the research questions you will actually run.
