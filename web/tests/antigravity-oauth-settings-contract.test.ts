import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const CARD = path.resolve(
  process.cwd(),
  "components/settings/AntigravityOAuthCard.tsx",
);
const CLIENT = path.resolve(process.cwd(), "lib/antigravity-oauth.ts");
const EN = path.resolve(process.cwd(), "locales/en/app.json");
const ZH = path.resolve(process.cwd(), "locales/zh/app.json");

test("Antigravity OAuth start payload includes loopback", () => {
  const client = readFileSync(CLIENT, "utf8");
  assert.match(client, /loopback\?: boolean/);
  assert.match(client, /\/api\/settings\/providers\/google-antigravity\/oauth/);
});

test("Antigravity OAuth card explains Firefox localhost failure", () => {
  const card = readFileSync(CARD, "utf8");
  const en = JSON.parse(readFileSync(EN, "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(ZH, "utf8")) as Record<string, string>;
  const firefoxHint =
    "Firefox cannot connect to localhost:51121. That is expected on a remote host or HTTPS reverse proxy. Copy the full address bar URL (it starts with http://localhost:51121/oauth-callback?code=) and paste it below. Do not close that tab first.";

  assert.match(card, /loginStart\.loopback/);
  assert.match(card, /localhost:51121\/oauth-callback\?code=/);
  assert.equal(en[firefoxHint], firefoxHint);
  assert.ok(zh[firefoxHint]);
});
