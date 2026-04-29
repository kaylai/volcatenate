# Backend models, repos, and citations

volcatenate is a thin Python wrapper. Every numerical result it produces comes from one of the underlying model packages listed below. **If you use volcatenate in published work, please cite both volcatenate _and_ the upstream model(s) whose results you reported.** This page collects the code repositories, online docs (where they exist), and the manuscripts that introduce or update each model — with downloadable PDFs of the papers themselves.

The information on this page mirrors the model-citation block in the [Sulfur Comparison Paper](https://github.com/PennyWieser/Sulfur_Comparison_Paper) README.

---

## D-Compress

**Code / executable:** <https://www.isterre.fr/annuaire/pages-web-du-personnel/alain-burgisser/article/software.html>

**Manual:** {download}`DCompress User Manual <papers/dcompress/DCompress_User_Manual.pdf>` — _bundled with the D-Compress distribution._

**Citation:**

- Burgisser, A., Alleti, M. & Scaillet, B. (2015). Simulating the behavior of volatiles belonging to the C–O–H–S system in silicate melts under magmatic conditions with the software D-Compress. _Computers & Geosciences_. [doi:10.1016/j.cageo.2015.03.002](https://doi.org/10.1016/j.cageo.2015.03.002) — {download}`PDF <papers/dcompress/Burgisser2015.pdf>` · {download}`Appendix B <papers/dcompress/Burgisser2015_Appendix_B.pdf>`

---

## EVo

**Code:** <https://github.com/pipliggins/EVo>

**Online documentation:** <https://evo-outgas.readthedocs.io/en/latest/>

**Citations:**

- _First publication of EVo._ Liggins, P., Shorttle, O. & Rimmer, P. B. (2020). Can volcanism build hydrogen-rich early atmospheres? _Earth and Planetary Science Letters_, 550, 116546. [doi:10.1016/j.epsl.2020.116546](https://doi.org/10.1016/j.epsl.2020.116546) — {download}`PDF <papers/evo/Liggins2020.pdf>`
- _More recent citation, with the current changes to the sulfur model._ Liggins, P., Jordan, S., Rimmer, P. B. & Shorttle, O. (2022). Growth and evolution of secondary volcanic atmospheres I: Identifying the geological character of hot rocky planets. _Journal of Geophysical Research: Planets_, 127. [doi:10.1029/2021JE007123](https://doi.org/10.1029/2021JE007123) — {download}`PDF <papers/evo/Liggins2022.pdf>`

---

## MAGEC

**Code:** No public repository. The compiled MATLAB solver (`.p` files) is distributed as supplementary material with Sun & Yao (2024); see the manuscript for details.

**Citations:**

- _Original MAGEC presentation._ Sun, C. & Lee, C.-T. A. (2022). Redox evolution of crystallizing magmas with C-H-O-S volatiles and its implications for atmospheric oxygenation. _Geochimica et Cosmochimica Acta_, 338, 302–321. [doi:10.1016/j.gca.2022.09.044](https://doi.org/10.1016/j.gca.2022.09.044) — {download}`PDF <papers/magec/SunLee2022.pdf>`
- _Current version of the Fe redox model used in volcatenate._ Sun, C. & Yao, L. (2024). Redox equilibria of iron in low- to high-silica melts: A simple model and its applications to C-H-O-S degassing. _Earth and Planetary Science Letters_, 638, 118742. [doi:10.1016/j.epsl.2024.118742](https://doi.org/10.1016/j.epsl.2024.118742) — {download}`PDF <papers/magec/SunYao2024.pdf>`

---

## Sulfur_X

**Code:** <https://github.com/sdecho/Sulfur_X>

**Citation:**

- Ding, S., Plank, T., Wallace, P. J. & Rasmussen, D. J. (2023). Sulfur_X: A model of sulfur degassing during magma ascent. _Geochemistry, Geophysics, Geosystems_, 24. [doi:10.1029/2022GC010552](https://doi.org/10.1029/2022GC010552) — {download}`PDF <papers/sulfurx/Ding2023.pdf>` · {download}`Supplement <papers/sulfurx/Ding2023_supplement.pdf>`

---

## VolFe

**Code:** <https://github.com/eryhughes/VolFe>

**Online documentation:** see the `docs/` directory in the VolFe repository.

**Citations:**

- _Sulfur solubility framework underpinning VolFe._ Hughes, E. C., Saper, L. M., Liggins, P., O'Neill, H. S. C. & Stolper, E. M. (2023). The sulfur solubility minimum and maximum in silicate melt. _Journal of the Geological Society_, 180(3), jgs2021–125. [doi:10.1144/jgs2021-125](https://doi.org/10.1144/jgs2021-125) — {download}`PDF <papers/volfe/Huges2023.pdf>`
- _Effects of fO₂ and S on vapor-saturation pressure._ Hughes, E. C., Liggins, P., Saper, L. & Stolper, E. M. (2024). The effects of oxygen fugacity and sulfur on the pressure of vapor-saturation of magma. _American Mineralogist_. [doi:10.2138/am-2022-8739](https://doi.org/10.2138/am-2022-8739) — {download}`PDF <papers/volfe/Hughes2024.pdf>`

---

## VESIcal

**Code:** <https://github.com/kaylai/VESIcal>

**Online documentation:** <https://vesical.readthedocs.io/en/latest/>

**Web app:** <https://vesical.anvil.app>

**Citations:**

- _Model description._ Iacovino, K., Matthews, S., Wieser, P. E., Moore, G. M. & Bégué, F. (2021). VESIcal Part I: An open-source thermodynamic model engine for mixed volatile (H₂O–CO₂) solubility in silicate melts. _Earth and Space Science_. [doi:10.1029/2020EA001584](https://doi.org/10.1029/2020EA001584) — {download}`PDF <papers/vesical/Iacovino2021_PartI.pdf>` · {download}`Supplement <papers/vesical/Iacovino2021_PartI_Supplement.pdf>`
- _Overview of solubility models and intercomparison._ Wieser, P. E., Iacovino, K., Matthews, S., Moore, G. & Allison, C. M. (2022). VESIcal Part II: A critical approach to volatile solubility modelling using an open-source Python3 engine. _Earth and Space Science_. [doi:10.1029/2021EA001932](https://doi.org/10.1029/2021EA001932) — {download}`PDF <papers/vesical/Wieser2022_PartII.pdf>` · {download}`Supplement <papers/vesical/Wieser2022_PartII_Supplement.pdf>`

---

## How to cite volcatenate itself

A volcatenate citation entry will be added here once the package has a registered DOI. Until then, cite the GitHub release tag and commit hash you used (visible in the `run_bundle.json` produced by every run).
