## 2026-05-27 - Indirect Prompt Injection via User Intent Text
**Vulnerability:** User intent text was directly embedded in LLM prompt parts.
**Learning:** Even with json encoding, LLMs can be manipulated semantically when reading user inputs (e.g., "Ignore previous instructions").
**Prevention:** Wrap untrusted user input within XML tags and explicitly instruct the LLM to treat the content strictly as data to be classified, ignoring any instructions within the XML tag.
