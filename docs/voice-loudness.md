# How the practised voice is made louder

Every practice track ("soprano 1 with accompaniment.mp3" etc.) should let the singer hear their own voice clearly above all other parts. This page explains how the volumes are calculated and why the formulas look the way they do. No prior knowledge of acoustics is assumed.

## Why fixed volume factors are not enough

Each voice is rendered with a different instrument (by default pan flute, recorder and two string ensembles). These instruments are not equally loud: with the FluidR3 soundfont the string ensemble used for the bass came out about 10 dB louder than the flutes. A fixed rule like "own voice 100 %, others 33 %" therefore produced practice tracks in which the alto was quieter than the rest. Even with one instrument for all voices, three voices at 33 % together are almost as loud as the own voice (see the example below).

So the volumes are now calculated from measurements instead of being fixed.

## The units: logarithm and decibel

### Logarithm to base 10

$`\log_{10}(x)`$ answers the question "10 to the power of what gives x?":

| x | 1 | 2 | 3 | 10 | 100 | 1000 |
|---|---|---|---|---|---|---|
| $`\log_{10}(x)`$ | 0 | 0.30 | 0.48 | 1 | 2 | 3 |

It turns multiplication into addition: $`\log_{10}(a \cdot b) = \log_{10}(a) + \log_{10}(b)`$, and $`\log_{10}(a^2) = 2 \cdot \log_{10}(a)`$.

### Decibel (dB)

Our ears don't perceive loudness linearly: twice the sound energy sounds only "a bit louder", not twice as loud. That is why loudness differences are given on a logarithmic scale, in decibels. A decibel always describes a **ratio** of two energies:

```math
\text{difference in dB} = 10 \cdot \log_{10}\left(\frac{\text{energy}_1}{\text{energy}_2}\right)
```

The 10 comes from the definition: a "bel" is $`\log_{10}`$ of the energy ratio, and a decibel is a tenth of a bel. Some useful values:

| energy ratio | 2x | 3x | 4x | 10x | 100x |
|---|---|---|---|---|---|
| dB | +3 | +4.8 | +6 | +10 | +20 |

Audio files measure levels relative to the loudest possible signal ("dB full scale", dBFS), so levels are negative numbers: -26 dB is louder than -46 dB.

### Amplitude and why the formula uses 20

In the program we don't change energies directly. We multiply the audio samples, i.e. how far the sound wave swings (the **amplitude**), by a factor. The energy of a signal is the **square** of its amplitude: twice the amplitude means four times the energy.

Putting this into the decibel formula:

```math
\text{dB} = 10 \cdot \log_{10}(\text{amplitude}^2) = 2 \cdot 10 \cdot \log_{10}(\text{amplitude}) = 20 \cdot \log_{10}(\text{amplitude})
```

So for amplitude factors the formula has 20 instead of 10. The 20 is not a tuning value, it follows from the definition. Solved for the factor:

```math
\text{amplitude factor} = 10^{\text{dB} / 20}
```

In the code this is the function `decibel_to_amplitude`. Examples: +6 dB is a factor of 2, -20 dB a factor of 0.1, -9.6 dB a factor of 0.33.

## The calculation step by step

### 1. Measure each voice

After each voice has been rendered to its own mp3, its average loudness (RMS level in dB) is measured with `sox stats`. Rests are cut out first (`measure_level`), otherwise a voice with many rests would count as quiet even though it sings just as loud as the others.

### 2. Bring all voices to the same loudness

Each voice is multiplied by $`10^{-\text{level} / 20}`$, which lifts it to 0 dB (`loudness_normalizing_gain`). Example:

| voice | measured level | needed change | factor |
|---|---|---|---|
| alto | -46 dB | +46 dB | $`10^{46/20} \approx 200`$ |
| bass | -26 dB | +26 dB | $`10^{26/20} = 20`$ |

Afterwards all voices are equally loud. The large factors are no problem because everything is scaled down together in step 4.

### 3. Lower the other voices

Independent voices add up their **energies**. Three equally loud voices together have three times the energy of one voice, so they are $`10 \cdot \log_{10}(3) \approx 4.8`$ dB louder than one of them. With $`n`$ other voices the rest is $`10 \cdot \log_{10}(n)`$ dB louder than a single voice.

The goal is that the practised voice is `margin` dB (default 8, option `-m`) louder than **all other parts together**. So each other voice is lowered by:

```math
\text{margin} + 10 \cdot \log_{10}(n)
```

For a SATB choir (3 other voices) that is 8 + 4.8 = 12.8 dB, a factor of about 0.23 (`accompaniment_gains`). With 7 other voices (SSAATTBB) it is 8 + 8.5 = 16.5 dB. The instrumental accompaniment is `instrumental_volume` times as loud as each other voice (option `-iv`, default 2.0 = +6 dB) and counts with its energy, $`\text{instrumental volume}^2`$, into $`n`$.

**Comparison with the old fixed factors:** 0.33 is $`20 \cdot \log_{10}(0.33) \approx -9.6`$ dB per voice. Three such voices together: -9.6 + 4.8 = -4.8 dB. The practised voice was only about 5 dB above the rest, and only if all instruments were equally loud.

### 4. Prevent distortion

The factors from steps 2 and 3 are all multiplied by the same number so that the loudest possible peak of the mix stays at 90 % of full scale (`mix_parts`). Because all parts are scaled together, the ratios between them don't change.

## Time-dependent balance (piano and forte passages)

Steps 1 to 4 set one volume per voice for the whole piece. Where the practised voice sings piano while the others sing forte, it would still be covered in that passage. So the practice tracks with accompaniment get a second, time-dependent correction (`balance_curve`):

1. The practised voice and the sum of all other parts are cut into short pieces of 50 ms (`BALANCE_HOP_S`). For each piece the energy is calculated, averaged over 0.4 s (`BALANCE_WINDOW_S`) so that a single short note doesn't change anything.
2. Where the practised voice sings and the rest is closer to it than $`\text{margin}`$ dB, the rest is lowered just enough to restore the distance. The allowed energy of the rest is $`\dfrac{\text{own energy}}{10^{\text{margin} / 10}}`$. Here the formula has 10 instead of 20 because we are comparing energies, not amplitudes.
3. The factor for the samples is $`\sqrt{\dfrac{\text{allowed energy}}{\text{actual energy}}}`$, because energy is the square of the amplitude. Example: if the rest has 4 times the allowed energy, its samples are multiplied by $`\sqrt{1/4} = 0.5`$ (-6 dB).
4. The rest is lowered by at most 12 dB (`MAX_BALANCE_REDUCTION_DECIBEL`, a factor of 0.25), so it never disappears completely.
5. The factor is lowered a little before and raised a little after each such passage, and the transitions are smoothed, so the other parts fade instead of jumping.
6. Where the practised voice rests or is already loud enough, the factor stays 1: the piano and forte of the score are kept.

Finally the whole mix is scaled so its highest peak is at 90 % of full scale, as in step 4.

## Values that can be tuned

These constants at the top of `midi_to_part_mp3s.py` are choices, not physics, and are best adjusted by listening:

| constant | default | meaning |
|---|---|---|
| `DEFAULT_VOICE_MARGIN_DECIBEL` | 8 dB | how far the practised voice is above the rest (option `-m`) |
| `MIX_PEAK_AMPLITUDE` | 0.9 | highest peak of a mix, as a fraction of full scale |
| `BALANCE_HOP_S` | 0.05 s | step size of the time-dependent balance |
| `BALANCE_WINDOW_S` | 0.4 s | how long a passage is before the balance reacts to it |
| `MAX_BALANCE_REDUCTION_DECIBEL` | 12 dB | the most the other parts are lowered in a passage |

## Limits

- **Notes sung in unison:** The energy rule in step 3 holds for independent voices. Where voices sing exactly the same notes, their waves add up directly and the rest can be up to 3 dB louder than calculated.
- **Dynamics:** The time-dependent balance lowers the rest by at most 12 dB. If the practised voice sings much more quietly than the others, it can still be less than `margin` dB above them in that passage.
- **Soundfont:** The measurements happen on the rendered audio, so the calculation adapts to whichever soundfont is installed.
