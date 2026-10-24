# KIN demo script (90 seconds + Q&A)

Pre-flight (10 min before): `.env` has two teammates' `MODEL_API_KEY`s, Deepgram and ElevenLabs keys; backend on :8000, frontend on :5173 on BOTH laptops (or one laptop + phone on the same LAN); run `python -m eval.run_eval` once so `eval/results.md` is fresh; open the Fade tab once and run Week 1 then Reset; backup video ready.

Laptop A = grandparent (Tamil speaker). Laptop B = grandchild (Arjun). Same call id on both. Phone = optional Twilio dial-in.

1. **(10 s) Problem.** "Three of us have grandparents we can't fully talk to."
2. **(25 s) Live call.** A clicks New call, joins as grandparent; B joins as grandchild with the same id. A speaks (or types):
   - `ரவி நேத்து அடையாறுலேர்ந்து போன் பண்ணான்.` → B hears English in the cloned voice; transcript shows **ரவி → your uncle Ravi mama (Mom's younger brother)**. Say: "Apple would say 'Ravi called'. We know *which* Ravi, from Adyar."
   - `ரவி கோவையில புது கடை திறந்திருக்காரு.` → **ரவி → your uncle Ravi periyappa (Dad's elder brother)**. "Same name, other side of the family, and the honorific verb ending gave it away."
3. **(15 s) Side-by-side.** Scroll to *Generic vs grounded*, hit Compare on the Coimbatore sentence. Read the eval line from `eval/results.md`: generic X% entity error vs grounded Y% on 105 sentences.
4. **(15 s) Fade.** Fade tab → Week 1 (everything translated) → Week 8 (nine words stay in Tamil, kin term still protected, curves visible). "Apple's translator is a crutch. Ours is physical therapy."
5. **(15 s) Muse.** On a phone with KIN added as a custom connector: "Muse, what did Ammamma say about her knee last week?" → answer from `/api/v1/memory/search`. Backup: the screen recording.
6. **(10 s) Close.** "Audio is processed in two-second windows and discarded; only transcripts and the family graph persist, on the family's own account. The goal is for KIN to become unnecessary."

Optional (if Phase 5 is live): grandparent dials the Twilio number from a plain phone; laptop B hears English. Needs `PUBLIC_WSS_HOST` (ngrok) and the Twilio number's voice webhook set to `https://<host>/twilio/voice`.

Fallbacks: no mic/ASR → type the lines; no LLM → the transcript shows the linker-only rendering (still grounded); no ElevenLabs → the stock tone, keep talking.
