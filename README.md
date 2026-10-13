# transit-parser
A set of scripts for parsing transit data into Vega-Lite JSON.

## Usage

`download_data.py` downloads each agency's ridership data into `../transit-data/`, and
`generate_data.py` generates the chart data from it into `../transit-charts/data/`:

```sh
python download_data.py nyc-subway
python generate_data.py nyc-subway
```

The downloaded data is laid out as:

- `original/`: files as downloaded from each agency, zstd-compressed.
- `processed/`: intermediate data computed from the downloads, where a step in between is useful.

## Related repositories

- [transit-charts](https://github.com/kevinji/transit-charts): The [transitcharts.com](https://transitcharts.com) website, which charts the generated data.
