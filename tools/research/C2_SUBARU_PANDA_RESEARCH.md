# C2 Subaru Panda research

## Scope

This branch is an isolated research path for Craig's C2-era DragonPilot install and
2018 Subaru Impreza. It is intentionally separate from `c2-subaru-improvements`,
which remains on the legacy 2047 Subaru steering ceiling.

Do not treat this branch as evidence that every early Impreza/Crosstrek EPS safely
accepts 3071.

## Vehicle evidence

Detected vehicle:

- `SUBARU IMPREZA LIMITED 2019` (legacy `CAR.IMPREZA` identifier)
- EPS firmware: `7ac00a00` / `b'z\xc0\n\x00'`
- existing Panda safety model: Subaru, safetyParam 0
- existing host ceiling: 2047

The baseline road log showed repeated final CAN-command saturation at +/-2047,
including sustained under-achievement before driver interventions on tighter
corners. This supports testing additional steering authority, but does not prove
that this exact EPS revision is safe at the historical 3071 ceiling.

## Public historical evidence

The earlier Subaru 3071 work established an alternate 3071 command ceiling for
some early Impreza/Crosstrek EPS. Later sunnypilot gating explicitly identified:

- `7ac00000`
- `7ac00400`
- `7ac00800`
- `8ac00000`

Craig's `7ac00a00` firmware appears in Subaru firmware databases, but no public
issue/PR was found that specifically documents it being tested at 3071.

For that reason this branch keeps `7ac00a00` in a separate research set instead
of adding it to the community-tested allowlist.

## Panda source provenance

The original public DragonPilot `deprecated-release2_e2e` branch contains the
same stripped Panda artifacts as Craig's fork:

- `panda.bin.signed` Git blob: `cf26f8b6e544b294055c280004757739a762b576`
- retained Panda Python after the 2023-02-08 ALKA refactor:
  `22543b9080109b41eef4732653c37626a217b957`

Several unchanged retained Python files match
`dragonpilot/panda@1d732d4747ea81c199906e9f1fc620911fb8add0` byte-for-byte.
That late-2022 revision also uses the C2-compatible CAN packet v3 protocol and
contains the same Subaru 2047 steering safety constraints.

The February 2023 DragonPilot release then layered its ALKA alternative-experience
behavior and a private C2 health-packet extension onto that older Panda line.

## Research Panda profile

The CI patcher reconstructs the relevant C2 behavior and adds a separate
`safetyParam` bit 2 profile:

| Profile | safetyParam | max steer |
| --- | ---: | ---: |
| stock Subaru | 0 | 2047 |
| Subaru Gen2 | 1 | 1000 |
| early-Impreza research | 2 | 3071 |

The research profile deliberately leaves these safety constraints unchanged:

- max real-time delta: 940
- real-time interval: 250000 us
- rate up: 50
- rate down: 70
- driver torque allowance: 60
- driver torque factor: 50
- torque safety type: driver-limited

## Host staging

The host side has an explicit-off-by-default DragonPilot parameter:

`dp_subaru_high_torque_research`

It only selects safetyParam 2 when:

1. the candidate is the old `CAR.IMPREZA` interface,
2. EPS firmware is exactly `7ac00a00`, and
3. the research parameter is explicitly enabled.

For the first A/B road test, the host ceiling is intentionally only **2300**.
The Panda research profile's 3071 value is an absolute safety ceiling, not the
initial requested operating ceiling.

The first test deliberately keeps the existing lateral controller/tune and
0.4 s actuator-delay value to isolate the effect of added authority.

## Build/signing gate

CI builds the reconstructed F4 Panda firmware with the public debug certificate.
That image must **not** be flashed until the installed C2 Panda bootstub is proven
to accept debug signatures. A release-only bootstub will reject it.

Before any flash:

- preserve the original `panda.bin.signed` and bootstub artifacts,
- verify packaged/live Panda hardware/version where possible,
- verify bootstub DEBUG vs RELEASE build,
- keep the current 2047 host branch available for rollback,
- only enable the host research parameter after Panda safetyParam 2 support is
  confirmed on the device.

## Test progression

1. Baseline: 2047 log already captured.
2. First staged host ceiling: 2300.
3. Compare saturation duration, desired-vs-actual lateral acceleration, driver
   interventions, EPS faults, and subjective path tracking on the same type of road.
4. Only consider a higher host ceiling if the 2300 stage remains saturated and
   under-achieves without introducing overshoot/faults.
