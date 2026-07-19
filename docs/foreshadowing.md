# Foreshadowing analysis

The analyzer counts planned, setup, progressed, paid-off, unresolved, early, repeated,
late, and setup-less payoff states. It records setup/payoff distance and accepted evidence,
then calculates a payoff rate. Setup must precede payoff, a paid item cannot be paid twice,
and important items expected by the ending can block automatic acceptance. Low-priority
open threads are allowed but remain explicit. A payoff without setup is reported as a
deus-ex-machina risk rather than silently rewritten.
