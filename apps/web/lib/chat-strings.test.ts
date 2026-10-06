// The /chat chrome follows the session's conversation language (spec 07 AC-16 to AC-22): no English in ES or PT.
import assert from "node:assert/strict";
import test from "node:test";
import { CHAT_STRINGS } from "./chat-strings.ts";
import { chipLabel } from "./demo.ts";

const ENGLISH = [
  "Sign out",
  "Pick a charge to dispute",
  "Register a test charge",
  "Amount",
  "Store name",
  "Register ",
  "Try a type of customer",
  "test charge",
  "Aggressive",
  "Passive",
  "Terse",
  "Verbose",
  "Confused",
  "Code-switching",
];

test("spec 07 AC-16: the chat chrome and demo tools carry no English in Spanish or Portuguese", () => {
  for (const lang of ["es", "pt"] as const) {
    const texts: string[] = [
      CHAT_STRINGS.signOut[lang],
      CHAT_STRINGS.pickTitle[lang],
      CHAT_STRINGS.testTitle[lang],
      CHAT_STRINGS.amountPlaceholder[lang],
      CHAT_STRINGS.amountLabel[lang],
      CHAT_STRINGS.merchantPlaceholder[lang],
      CHAT_STRINGS.register[lang],
      CHAT_STRINGS.personasTitle[lang],
      CHAT_STRINGS.testChargeTag[lang],
      CHAT_STRINGS.registered[lang]("1.00", "MXN", "Tienda"),
      chipLabel({ date: "2026-05-01", amount: 1, currency: "MXN", merchant: "Tienda", synthetic: true } as never, CHAT_STRINGS.testChargeTag[lang]),
      ...Object.values(CHAT_STRINGS.personas).map((b) => b[lang]),
    ];
    for (const text of texts) {
      for (const word of ENGLISH) assert.ok(!(text + " ").includes(word), `${lang}: "${text}" contains "${word}"`);
    }
  }
});
