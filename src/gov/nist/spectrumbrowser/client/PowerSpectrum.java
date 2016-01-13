package gov.nist.spectrumbrowser.client;

import gov.nist.spectrumbrowser.common.SpectrumBrowserCallback;

import java.util.logging.Level;
import java.util.logging.Logger;

import com.google.gwt.core.client.GWT;
import com.google.gwt.event.dom.client.LoadEvent;
import com.google.gwt.event.dom.client.LoadHandler;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONParser;
import com.google.gwt.json.client.JSONValue;
import com.google.gwt.user.client.ui.HTML;
import com.google.gwt.user.client.ui.HorizontalPanel;
import com.google.gwt.user.client.ui.Image;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.RootPanel;
import com.google.gwt.user.client.ui.VerticalPanel;
import com.googlecode.gwt.charts.client.ChartLoader;
import com.googlecode.gwt.charts.client.ChartPackage;
import com.googlecode.gwt.charts.client.ColumnType;
import com.googlecode.gwt.charts.client.DataTable;
import com.googlecode.gwt.charts.client.corechart.LineChartOptions;
import com.googlecode.gwt.charts.client.corechart.ScatterChart;
import com.googlecode.gwt.charts.client.corechart.ScatterChartOptions;
import com.googlecode.gwt.charts.client.options.HAxis;
import com.googlecode.gwt.charts.client.options.VAxis;
import com.reveregroup.gwt.imagepreloader.FitImage;

public class PowerSpectrum implements SpectrumBrowserCallback<String> {

	private VerticalPanel vpanel;
	private SpectrumBrowser spectrumBrowser;
	private int width;
	private int height;
	private String sensorId;

	private static Logger logger = Logger.getLogger("SpectrumBrowser");

	public PowerSpectrum(SpectrumBrowser spectrumBrowser, VerticalPanel vpanel,
			String sensorId, long startTime, long milisecondOffset, int width,
			int height) {
		this.sensorId = sensorId;
		this.vpanel = vpanel;
		this.spectrumBrowser = spectrumBrowser;
		this.width = width;
		this.height = height;
		this.spectrumBrowser.getSpectrumBrowserService().generateSpectrum(
				sensorId, startTime, milisecondOffset, this);
	}

	public PowerSpectrum(SpectrumBrowser spectrumBrowser, VerticalPanel vpanel,
			String sensorId, long startTime, double hourOffset, int width,
			int height) {
		int secondOffset = (int) (hourOffset * 60 * 60);
		this.sensorId = sensorId;
		this.spectrumBrowser = spectrumBrowser;
		this.width = width;
		this.height = height;
		this.vpanel = vpanel;
		this.spectrumBrowser.getSpectrumBrowserService().generateSpectrum(
				sensorId, startTime, secondOffset, this);
	}

	public PowerSpectrum(SpectrumBrowser spectrumBrowser, VerticalPanel vpanel,
			String sensorId, long startTime, double hourOffset,
			long subBandMinFreq, long subBandMaxFreq, int width, int height) {
		int secondOffset = (int) (hourOffset * 60 * 60);
		this.spectrumBrowser = spectrumBrowser;
		this.width = width;
		this.height = height;
		this.vpanel = vpanel;
		this.spectrumBrowser.getSpectrumBrowserService().generateSpectrum(
				sensorId, startTime, secondOffset, subBandMinFreq,
				subBandMaxFreq, this);
	}
	
	protected float round2(double val) {
		return (float) ((int) ((val + .005) * 100) / 100.0);
	}
	

	@Override
	public void onSuccess(String result) {

		JSONValue jsonValue = JSONParser.parseLenient(result);
		final JSONArray frequencyData = jsonValue.isObject().get("freqArray")
				.isArray();
		final JSONArray spectrumData = jsonValue.isObject().get("spectrumData")
				.isArray();
		final JSONArray noiseFloorData = jsonValue.isObject()
				.get("noiseFloorData").isArray();
		final String title = jsonValue.isObject().get("title").isString().stringValue();
		final String xlabel = jsonValue.isObject().get("xlabel").isString().stringValue();
		final String ylabel = jsonValue.isObject().get("ylabel").isString().stringValue();
		ChartLoader chartLoader = new ChartLoader(ChartPackage.CORECHART);

		chartLoader.loadApi(new Runnable() {
			@Override
			public void run() {
				try {
					DataTable dataTable = DataTable.create();
					dataTable.addRows(spectrumData.size());
					dataTable.addColumn(ColumnType.NUMBER, xlabel);
					dataTable.addColumn(ColumnType.NUMBER, "Signal");
					dataTable.addColumn(ColumnType.NUMBER, "Noise Floor");
					for (int i = 0; i < spectrumData.size(); i++) {
						double freq = frequencyData.get(i).isNumber()
								.doubleValue();
						double signalPower = spectrumData.get(i).isNumber()
								.doubleValue();
						double noiseFloor = noiseFloorData.get(i).isNumber()
								.doubleValue();
						dataTable.setCell(i, 0, freq, "Frequency (MHz) : " + freq );
						dataTable.setCell(i, 1, signalPower, "Signal Power (dBm): " +  round2(signalPower) );
						dataTable.setCell(i, 2, noiseFloor, "Noise Floor (dBm): " + round2(noiseFloor) );
					}
					ScatterChart spectrumChart = new ScatterChart();
					spectrumChart.setHeight(height + "px");
					spectrumChart.setWidth(width + "px");
					spectrumChart.setPixelSize(width, height);
					ScatterChartOptions options = ScatterChartOptions.create();
					options.setBackgroundColor("#f0f0f0");
					options.setPointSize(2);
					options.setHeight(height);
					options.setWidth(width);
					HAxis haxis = HAxis.create(xlabel);
					VAxis vaxis = VAxis.create(ylabel);
					options.setHAxis(haxis);
					options.setVAxis(vaxis);
					
					spectrumChart.draw(dataTable, options);
					HTML html = new HTML("<h3>" + title + "</h3>");
					vpanel.add(html);
					vpanel.add(spectrumChart);
				} catch (Throwable th) {
					logger.log(Level.SEVERE,
							"Exception in processing response", th);
				}
			}
		});

	}

	@Override
	public void onFailure(Throwable throwable) {
		spectrumBrowser.displayError("Error communicating with the server");
	}

}
