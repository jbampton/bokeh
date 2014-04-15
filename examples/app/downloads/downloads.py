import datetime
import pandas as pd

import logging
logging.basicConfig(level=logging.INFO)

from bokeh.widgetobjects import VBoxModelForm, HBox, VBox, BokehApplet, Select, Slider, DatePicker
from bokeh.objects import (Plot, ColumnDataSource, Range1d, DataRange1d, FactorRange, Glyph,
    LinearAxis, DatetimeAxis, CategoricalAxis, Grid, HoverTool, DaysTicker, BasicTickFormatter)
from bokeh.glyphs import Line, Circle, Rect
from bokeh.properties import Dict, Float, String, Instance, Enum, Date, lookup_descriptor

def load_csv(filename):
    df = pd.read_csv(filename)
    df["date"] = pd.to_datetime(df.timestamp, unit='s')
    return df

installers = load_csv("data/installers.internalpanel.data.log")
packages = load_csv("data/pkgs.internalpanel.data.log")

class InstallersModel(VBoxModelForm):
    installer = Enum("All", *sorted(installers.event.unique()))
    resolution = Enum("daily", "monthly", "yearly", default="monthly")
    platform = Enum("All", *sorted(installers.platform.unique()))
    arch = Enum("All", *sorted(installers.arch.unique()))
    start = Date(installers.date.min().date())
    end = Date(installers.date.max().date())

    input_specs = [{
        "widget": Select,
        "name": "installer",
        "title": "Installer:",
        "value": installer.default,
        "options": installer.allowed_values,
    }, {
        "widget": Select,
        "name": "resolution",
        "title": "Resolution:",
        "value": resolution.default,
        "options": resolution.allowed_values,
    }, {
        "widget": Select,
        "name": "platform",
        "title": "Platform:",
        "value": platform.default,
        "options": platform.allowed_values,
    }, {
        "widget": Select,
        "name": "arch",
        "title": "Architecture:",
        "value": arch.default,
        "options": arch.allowed_values,
    }, {
        "widget": DatePicker,
        "name": "start",
        "title": "Start:",
        "value": start.default,
        "min_date": start.default,
    }, {
        "widget": DatePicker,
        "name": "end",
        "title": "End:",
        "value": end.default,
        "max_date": end.default,
    }]

class DownloadsApp(BokehApplet):
    downloads_source = Instance(ColumnDataSource, has_ref=True)
    punchcard_source = Instance(ColumnDataSource, has_ref=True)
    downloads_plot = Instance(Plot, has_ref=True)
    punchcard_plot = Instance(Plot, has_ref=True)

    def create(self, session):
        self.modelform = InstallersModel()
        self.modelform.create_inputs(session)

        self.downloads_source = ColumnDataSource(dict(
            dates       = [],
            downloads   = [],
        ))
        self.punchcard_source = ColumnDataSource(dict(
            counts      = [],
            percentages = [],
            hours       = sum([ [str(hour)]*7 for hour in xrange(0, 24) ], []),
            days        = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]*24,
        ))
        self.update_data()

        self.downloads_plot = self.make_downloads_plot(self.downloads_source)
        self.punchcard_plot = self.make_punchcard_plot(self.punchcard_source)

        self.children.append(self.modelform)
        self.children.append(VBox(children=[self.downloads_plot, self.punchcard_plot]))
        self.add_all(session)

    def make_downloads_plot(self, source):
        xdr = DataRange1d(sources=[source.columns("dates")])
        ydr = DataRange1d(sources=[source.columns("downloads")])
        title = "%s downloads" % self.modelform.installer
        plot = Plot(title=title, data_sources=[source], x_range=xdr, y_range=ydr, width=600, height=400)
        line = Line(x="dates", y="downloads", line_color="blue")
        line_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=line)
        plot.renderers.append(line_glyph)
        circle = Circle(x="dates", y="downloads", fill_color="red")
        circle_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=circle)
        plot.renderers.append(circle_glyph)
        hover = HoverTool(plot=plot, tooltips=dict(downloads="@downloads"))
        plot.tools.append(hover)
        yformatter = BasicTickFormatter(precision=None, use_scientific=False)
        xaxis = DatetimeAxis(plot=plot, dimension=0)
        yaxis = LinearAxis(plot=plot, dimension=1, formatter=yformatter)
        xgrid = Grid(plot=plot, dimension=0, axis=xaxis)
        ygrid = Grid(plot=plot, dimension=1, axis=yaxis)
        return plot

    def make_punchcard_plot(self, source):
        xdr = FactorRange(factors=source.data["hours"][::7])
        ydr = FactorRange(factors=source.data["days"][:7])
        title = "%s punchcard" % self.modelform.installer
        plot = Plot(title=title, data_sources=[source], x_range=xdr, y_range=ydr, width=600, height=400)
        rect = Rect(x="hours", y="days", width=1, height=1, fill_color="red", fill_alpha="percentages")
        rect_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=rect)
        plot.renderers.append(rect_glyph)
        hover = HoverTool(plot=plot, tooltips=dict(downloads="@counts"))
        plot.tools.append(hover)
        xaxis = CategoricalAxis(plot=plot, dimension=0)
        yaxis = CategoricalAxis(plot=plot, dimension=1)
        return plot

    def input_change(self, obj, attrname, old, new):
        self.update_data()
        self.downloads_plot.title = "%s downloads" % self.modelform.installer
        self.punchcard_plot.title = "%s punchcard" % self.modelform.installer

    def update_data(self):
        selected = installers

        selected = selected[selected.date >= self.modelform.start]
        selected = selected[selected.date <= self.modelform.end]

        installer = self.modelform.installer
        if installer != "All":
            selected = selected[selected.event == installer]

        platform = self.modelform.platform
        if platform != "All":
            selected = selected[selected.platform == platform]

        arch = self.modelform.arch
        if arch != "All":
            selected = selected[selected.arch == arch]

        resolution = self.modelform.resolution
        fn = dict(
            daily   = lambda x: datetime.date(x.year, x.month, x.day),
            monthly = lambda x: datetime.date(x.year, x.month, 1),
            yearly  = lambda x: datetime.date(x.year, 1, 1),
        )[resolution]

        dates = selected.date.map(fn)
        downloads = selected.groupby(dates).size()

        hours = selected.date.map(lambda x: x.hour)
        daysofweek = selected.date.map(lambda x: x.dayofweek)
        counts = selected.groupby([hours, daysofweek]).size()
        percentages = counts.astype(float)/counts.max()

        self.downloads_source.data.update(dict(
            dates       = downloads.index,
            downloads   = downloads.values,
        ))
        self.punchcard_source.data.update(dict(
            counts      = counts.values,
            percentages = percentages.values,
        ))

        self.downloads_source._dirty = True
        self.punchcard_source._dirty = True

DownloadsApp.add_route("/downloads", "http://localhost:5006")

if __name__ == "__main__":
    import bokeh.server
    bokeh.server.run()
