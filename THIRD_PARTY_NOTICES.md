# Third-party notices

The repository's MIT license applies to project-authored code. It does not replace the licenses or service terms of the following components and data sources.

## Apache ECharts 5.6.0

- File: `static/vendor/echarts.min.js`
- Source: <https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js>
- Project: <https://github.com/apache/echarts/tree/5.6.0>
- License: Apache License 2.0; original license and notice are retained as `static/vendor/echarts-LICENSE.txt` and `static/vendor/echarts-NOTICE.txt`.
- Copyright 2017-2024 The Apache Software Foundation.

The browser bundle also includes zrender 5.6.1 (BSD-3-Clause), TypeScript helpers from tslib 2.3.0 (0BSD), and portions derived from d3 (BSD-3-Clause). Their notices are retained in `static/vendor/zrender-LICENSE.txt`, `tslib-LICENSE.txt` and `echarts-LICENSE-d3.txt` respectively.

This product includes software developed at The Apache Software Foundation (<https://www.apache.org/>).

## Historical China map

- File: `static/data/china.json`
- Unmodified source: <https://raw.githubusercontent.com/apache/echarts/4.2.1/map/json/china.json>
- Source project: Apache ECharts 4.2.1, distributed under Apache License 2.0.
- Original license and notice are retained in `static/data/china-LICENSE.txt` and `static/data/china-NOTICE.txt`.
- This is a historical, generalized visualization asset. It is not a current administrative-boundary reference or navigation dataset.

The map is retained locally so rendering does not require a CDN at runtime. Place labels and city coordinates come from the separate city directory.

## City directory inherited from v1

`China-City-List-latest.csv` is inherited unchanged from Meteo-Command v1. Its filename and columns match the format used by the [QWeather Location List](https://github.com/qwd/LocationList); the original repository did not record its precise upstream version or separate data license. That format alone does not establish provenance or redistribution rights. No new license grant for this dataset is asserted by this release. The project's MIT code license must not be interpreted as a license for third-party geographic data.

## Online data

- Weather data: [Open-Meteo](https://open-meteo.com/), see [license](https://open-meteo.com/en/license) and [terms](https://open-meteo.com/en/terms).
- Air-quality data: [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api), including [Copernicus Atmosphere Monitoring Service (CAMS)](https://atmosphere.copernicus.eu/) model data. Acknowledge both Open-Meteo and CAMS when using this data.
- Data is model output with its own temporal resolution and uncertainty. Application-generated risk references are not official weather warnings.

Open-Meteo's free hosted service is subject to non-commercial terms and request limits. Its data licensing and API service entitlement are separate considerations.

## Python runtime and dependencies

The frozen desktop bundle includes Python and packages required by Flask, Requests and Waitress. Consult their upstream projects for the applicable terms:

- [Python](https://docs.python.org/3/license.html): Python Software Foundation License.
- [Flask / Pallets](https://flask.palletsprojects.com/en/stable/license/): BSD-3-Clause.
- [Requests](https://github.com/psf/requests/blob/main/LICENSE): Apache-2.0.
- [Waitress](https://github.com/Pylons/waitress/blob/main/LICENSE.txt): ZPL-2.1.
- Frozen-runtime support: [setuptools](https://github.com/pypa/setuptools) (MIT) and [packaging](https://github.com/pypa/packaging) (Apache-2.0 / BSD-2-Clause), including retained license texts for bundled components.

Dependency license texts are included in the release's `licenses/` directory by the packaging script.
