# 0029. Voice: Bedrock Voxtral speech-to-text on the api and the browser's text-to-speech

- **Status:** Accepted (lead decision D-072, 2026-10-05)
- **Date:** 2026-10-05
- **Deciders:** Freddy (lead) · **Owner:** @salazarvalverdeai
- **Related:** specs 05 (AC-24), 07 (AC-10) · ADRs 0009, 0017

## Context
- Customers report disputes by phone as much as by chat; speaking a claim lowers the effort of first contact.
- Everything runs in `us-east-2` (ADR 0009). Amazon Nova Sonic, the Bedrock speech-to-speech model, is offered only in
  `us-east-1`, and a real-time voice agent would also bypass the text path where the rules decide.
- Mistral Voxtral Mini 3B and Small 24B take speech through Converse and Invoke in-region in `us-east-2`
  ([model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-mistral-ai-voxtral-mini-3b-2507.html),
  read 2026-10-05; lifecycle Legacy, EOL 2027-03-30). Converse carries audio as an `audio` content block
  ([AudioBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_AudioBlock.html), read 2026-10-05).

## Decision
Voice is two halves around the unchanged text chat. The api transcribes a short clip with Voxtral Mini
(`POST /api/voice/transcribe`, configurable to Small) and returns only `{text, language}`; the web puts the text in the
composer as an editable draft, and the customer sends it like typed text. Replies are read aloud by the browser's
`speechSynthesis`. No audio is stored; each call is an `llm_calls` row under the daily cap and the abuse guard.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Voxtral STT + browser TTS (chosen) | in-region; the rules still decide on text; cents per thousand clips `[external]` | two halves to build; browser voices vary |
| Nova Sonic speech-to-speech | natural real-time dialogue | `us-east-1` only; bypasses the text path and its guardrails |
| Amazon Transcribe streaming | managed, many languages | another service, IAM and SDK surface for the api |
| Browser `SpeechRecognition` | free, no backend | Chrome sends audio to its own servers; missing in Firefox |
| ElevenLabs (agent platform or speech APIs) | the most natural voices; a ready real-time voice agent | customer audio and reply text leave AWS for a third-party processor; its agents run the dialogue and tool calls on the vendor's runtime, outside the graph where the rules decide; a voice flow invites spoken card numbers into that pipeline (PCI DSS scope); one more vendor contract and API key |

### Why not ElevenLabs
The first scope listed "voice in `/chat` with ElevenLabs" as optional (docs/README.md). It was dropped for this design
for four reasons; the synthetic data would have allowed an external service, so the reason is what a bank could deploy:
1. **Data boundary.** A customer's voice and the replies about their dispute would go to a processor outside the AWS
   account and region (ADR 0009). Voxtral runs in `us-east-2` under the same IAM role, and no audio is stored.
2. **The rules must keep deciding.** A hosted voice agent runs its own dialogue and calls tools from the vendor's
   runtime. Here the voice only becomes text, and that text goes through the same graph, guardrails and policy engine
   as typed text (constitution #1, #3).
3. **No card data by voice.** Voice agents commonly ask for the card number or a code out loud. Identity here comes
   from the session and the one-time code on screen, never from what the customer says, and a card number in the text
   is denied (POL-PII, G-IN-04). Keeping spoken card numbers out of a third-party pipeline also keeps it out of PCI
   DSS scope.
4. **Fewer secrets and vendors.** No extra API key to protect or contract to sign. Text-to-speech uses the browser's
   `speechSynthesis`, so reply text never leaves the device for speech.

## Consequences
- The constitution holds: the LLM only transcribes, the transcript goes through the same graph, a person closes.
- Voxtral invents sentences for silence or tones (live smoke 2026-10-05), so silent clips are not sent and the
  transcript is always a draft the customer can correct.
- The api image needs `boto3`, the price rows and `LLM_PROVIDER=bedrock` with the instance role's Bedrock access.

## Confidence
Medium. Revisit if Nova Sonic reaches `us-east-2`, if Voxtral leaves Bedrock (EOL 2027-03-30), or if ES/PT accents
from real customers transcribe poorly with Mini (switch `BEDROCK_MODEL_STT` to Small).
