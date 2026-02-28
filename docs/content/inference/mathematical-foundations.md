---
title: "Mathematical Foundations"
description: "Mathematical formulations behind Indexly's statistical inference engine."
weight: 42
type: docs
---


# Correlation

## Pearson Correlation

$$
r = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}
{\sqrt{\sum (x_i - \bar{x})^2 \sum (y_i - \bar{y})^2}}
$$

### Fisher Z Confidence Interval

$$
z = \tanh^{-1}(r) \newline 
SE = \frac{1}{\sqrt{n-3}} \newline
$$
$$z_{CI} = z \pm z_{\alpha/2} \cdot SE, \\quad CI = \tanh(z_{CI})$$


Used for all Pearson correlation CIs.

---

# T-Test (Independent)

$$
t = \frac{\bar{x}_1 - \bar{x}_2}
{\sqrt{\frac{s_1^2}{n_1} + \frac{s_2^2}{n_2}}}
$$

Degrees of freedom follow Welch correction when variances differ.

---

# Paired T-Test

$$
t = \frac{\bar{d}}{s_d / \sqrt{n}}
$$

where $d$ is the difference vector.

---

# ANOVA

$$
F = \frac{MS_{between}}{MS_{within}}
$$

Where:

$$
MS = \frac{SS}{df}
$$

Post-hoc uses Tukey HSD.

---

# Mann–Whitney U

Ranks pooled samples and evaluates difference in rank sums.

---

# Kruskal–Wallis

Nonparametric alternative to ANOVA based on ranked data.

---

# Confidence Interval (Mean)

$$
\bar{x} \pm t_{\alpha/2, df} \cdot \frac{s}{\sqrt{n}}
$$

---

# Confidence Interval (Proportion)

$$
\hat{p} \pm z_{\alpha/2} \sqrt{\frac{\hat{p}(1-\hat{p})}{n}}
$$

---

# Mean Difference CI

$$
(\bar{x}_1 - \bar{x}_2) \pm t_{\alpha/2} \cdot SE
$$

---

# Regression (OLS)

$$
\hat{\beta} = (X^TX)^{-1}X^Ty
$$

Standard errors derived from residual variance.

---

# Mixed Effects

$$
y = X\beta + Z\gamma + \epsilon
$$

Where:

- $X\beta$ fixed effects  
- $Z\gamma$ random effects

---

# Bootstrap

Resampling with replacement:

$$
\hat{\theta}^* = f(X^*)
$$

CI derived from empirical percentiles.

---

# Kruskal–Wallis (Effect Size)

The Kruskal–Wallis test evaluates whether rank distributions differ across groups.  
When the test is significant, an effect size should be reported to assess **practical significance**.

---

## Epsilon-Squared (ε²)

$$
\varepsilon^2 = \frac{H - k + 1}{n - k}
$$

Where:

- $H$ = Kruskal–Wallis statistic  
- $k$ = number of groups  
- $n$ = total sample size

### Interpretation Guidelines

* 0.01 → Small  
* 0.06 → Medium  
* 0.14 → Large

---

## Eta-Squared for Kruskal–Wallis (η²ₕ)

$$
\eta^2_H = \frac{H - k + 1}{n - 1}
$$

Where:

- $H$ = Kruskal–Wallis statistic  
- $k$ = number of groups  
- $n$ = total sample size

---

## Example Calculation

```python
H = 170.014
k = 7
n = 216000

epsilon_sq = (H - k + 1) / (n - k)
eta_sq_h = (H - k + 1) / (n - 1)

print("epsilon^2 =", epsilon_sq)
print("eta^2_H =", eta_sq_h)
````

Result:

$\varepsilon^2 \approx 0.00076 \\quad$ 
$\eta^2_H \approx 0.00076$

---

## Practical Interpretation

Although the Kruskal–Wallis test may be statistically significant (p < 0.0001),
an ε² ≈ 0.00076 indicates a **negligible practical effect**.

> Large sample sizes can produce statistical significance even when the real-world effect is extremely small.

---

# Next

* [MET Analysis with Indexly](mets-analysis.md)
* [Daily steps & MET values analysis](mets-steps-analysis.md)
* [Sleep Analysis](sleep-met-analysis.md)

See [Developer API](developer-api.md) for programmatic usage of the Indexly inference engine.

<!-- Load KaTeX CSS & JS for static math rendering -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {
          delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false}
          ],
          throwOnError: false,
          macros: { '\\RR': '\\mathbb{R}' }
        });"></script>

