package upstream

import "testing"

func TestTurnstileXORString(t *testing.T) {
	turnstile := Turnstile{}
	if decoded := turnstile.XORString(turnstile.XORString("challenge", "token"), "token"); decoded != "challenge" {
		t.Fatalf("got %q", decoded)
	}
}
