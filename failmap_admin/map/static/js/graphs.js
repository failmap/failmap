function d3stats() {
    // bl.ocks.org
    // https://bl.ocks.org/mbostock/3885211
    // https://www.mattlayman.com/2015/d3js-area-chart.html
    // https://github.com/d3/d3/blob/master/API.md
    var tooltip = d3.select("body")
        .append("div")
        .attr("class", "remove")
        .attr("class", "d3_tooltip")
        .style("visibility", "hidden")
        .style("top", "30px")
        .style("left", "55px");


    d3.json("data/vulnstats/0/index.json", function (error, data) {
        stacked_area_chart("tls_qualys", error, data.tls_qualys);
        stacked_area_chart("plain_https", error, data.plain_https);
        stacked_area_chart("security_headers_strict_transport_security", error, data.security_headers_strict_transport_security);
        stacked_area_chart("security_headers_x_frame_options", error, data.security_headers_x_frame_options);
        stacked_area_chart("security_headers_x_content_type_options", error, data.security_headers_x_content_type_options);
        stacked_area_chart("security_headers_x_xss_protection", error, data.security_headers_x_xss_protection);
    });

    // tooltip value.
    // this is declared globally, otherwise the value would be overwritten by the many "gaps" that are automatically
    // filled by SVG (see below)
    pro = 0;

    function stacked_area_chart(element, error, data) {
        // chart layout
        var svg = d3.select("#" + element),
            margin = {top: 20, right: 20, bottom: 30, left: 50},
            width = svg.attr("width") - margin.left - margin.right,
            height = svg.attr("height") - margin.top - margin.bottom;

        var parseDate = d3.timeParse("%Y-%m-%d");

        var x = d3.scaleTime().range([0, width]),
            y = d3.scaleLinear().range([height, 0]),
            z = d3.scaleOrdinal(['yellow', 'orange', 'red']);

        var stack = d3.stack();

        // https://bl.ocks.org/d3noob/ced1b9b18bd8192d2c898884033b5529
        var area = d3.area()
            .x(function (d, i) {
                return x(parseDate(d.data.date));
            })
            .y0(function (d) {
                return y(d[0]);
            })
            .y1(function (d) {
                return y(d[1]);
            })
            .curve(d3.curveMonotoneX);

        var g = svg.append("g")
            .attr("transform", "translate(" + margin.left + "," + margin.top + ")");


        // plotting values on the chart
        if (error) throw error;

        var keys = ["low", "medium", "high"];

        x.domain(d3.extent(data, function (d) {
            return parseDate(d.date);
        }));
        y.domain([0, d3.max(data, function (d) {
            return (d.high + d.medium + d.low);
        })]);

        stack.keys(keys);
        z.domain(keys);

        var layer = g.selectAll(".layer")
            .data(stack(data))
            .enter().append("g")
            .attr("class", "layer");

        layer.append("path")
            .attr("class", "area")
            .style("fill", function (d) {
                return z(d.key);
            })
            .attr("d", area);

        layer.filter(function (d) {
            return d[d.length - 1][1] - d[d.length - 1][0] > 0.01;
        })
            .append("text")
            .attr("x", width - 6)
            .attr("y", function (d) {
                return y((d[d.length - 1][0] + d[d.length - 1][1]) / 2);
            })
            .attr("dy", ".35em")
            .style("font", "10px sans-serif")
            .style("text-anchor", "end")
            .text(function (d) {
                // the switch is explicit for gettext translations
                if (d.key === "low")
                    return gettext("low");
                if (d.key === "medium")
                    return gettext("medium");
                if (d.key === "high")
                    return gettext("high");

                // and for any other cases we don't know yet.
                return d.key;
            });

        g.append("g")
            .attr("class", "axis axis--x")
            .attr("transform", "translate(0," + height + ")")
            //.ticks(d3.time.weeks);  Uncaught TypeError: Cannot read property 'weeks' of undefined
            .call(d3.axisBottom(x).ticks(4));

        //
        g.append("g")
            .attr("class", "axis axis--y")
            .call(d3.axisLeft(y).ticks(6));


        // taken from:
        // tooltips http://bl.ocks.org/WillTurman/4631136
        // with various customizations, especially in the hashing function for month + date
        // given: februari 1st = 2 + 1 = 3 and januari second = 1 + 2 = 3. Use isodates as strings and it works.
        var datearray = [];

        svg.selectAll(".layer")
            .attr("opacity", 1)
            .on("mouseover", function (d, i) {
                svg.selectAll(".layer").transition()
                    .duration(250)
                    .attr("opacity", function (d, j) {
                        return j !== i ? 0.6 : 1;
                    })
            })

            // calculating this every time the mouse moves seems a bit excessive.
            .on("mousemove", function (d, i) {
                // console.log("d");
                // console.log(d);
                mouse = d3.mouse(this);
                mousex = mouse[0];
                var invertedx = x.invert(mousex);
                // console.log(invertedx);

                // downsampling to days, using a hash function to find the correct value.
                invertedx = "" + invertedx.getFullYear() + invertedx.getMonth() + invertedx.getDate(); // nr of month day of the month
                // console.log("invertedx");
                // console.log(invertedx);
                var selected = d;
                for (var k = 0; k < selected.length; k++) {
                    // daite = Date(selected[k].data.date);
                    // console.log(daite.toLocaleString());
                    mydate = new Date(selected[k].data.date);
                    datearray[k] = "" + mydate.getFullYear() + mydate.getMonth() + mydate.getDate();
                }

                // invertedx can have any day value, for example; d3js does a fill of dates you don't have.
                // and invertedx can thus have one of those filled days that are not in your dataset.
                // therefore you can't read the data from your dataset and get a typeerror.
                // therefore we check on mousedate.

                // console.log("datearray");
                // console.log(datearray);
                // todo: we could find the date that's "closest by", but in the end the result will remain grainy
                // due to the filled dates.
                mousedate = datearray.indexOf(invertedx);  // returns -1 if not in index


                if (mousedate !== -1) {
                    pro = d[mousedate][1] - d[mousedate][0];
                }

                d3.select(this)
                    .classed("hover", true),
                    // mouse is the location of the mouse on the graph.
                    // v4 has clientx and clienty, which resembles the document.
                    tooltip.html("<p>" + d.key + "<br>" + pro + "</p>")
                        .style("visibility", "visible")
                        .style("top", (window.pageYOffset + d3.event.clientY + 25) + "px")
                        .style("left", (window.pageXOffset + d3.event.clientX) + "px");


            })
            .on("mouseout", function (d, i) {
                svg.selectAll(".layer")
                    .transition()
                    .duration(550)
                    .attr("opacity", "1");
                d3.select(this)
                    .classed("hover", false)
                    .attr("stroke-width", "0px"),
                    tooltip.html("<p>" + d.key + "<br>" + pro + "</p>")
                        .style("visibility", "hidden");
            });


    }
}