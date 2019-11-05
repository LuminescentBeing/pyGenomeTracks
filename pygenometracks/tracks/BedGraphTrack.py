from . GenomeTrack import GenomeTrack
from .. utilities import file_to_intervaltree, plot_coverage
import numpy as np
import pyBigWig

DEFAULT_BEDGRAPH_COLOR = '#a6cee3'


class BedGraphTrack(GenomeTrack):
    SUPPORTED_ENDINGS = ['.bg', '.bg.gz', '.bg.bgz',
                         '.bedgraph', '.bedgraph.gz', '.bedgraph.bgz',
                         '.bedGraph', '.bedGraph.gz', '.bedGraph.bgz',
                         '.bdg', '.bdg.gz', '.bdg.bgz']
    TRACK_TYPE = 'bedgraph'
    OPTIONS_TXT = GenomeTrack.OPTIONS_TXT + """
color = green
# to convert missing data (NaNs) into zeros. Otherwise, missing data is not plotted.
nans to zeros = True
# for type, the options are: line, points, fill. Default is fill
# to add the preferred line width or point size use:
# type = line:lw where lw (linewidth) is float
# similarly points:ms sets the point size (markersize (ms) to the given float
# type = line:0.5
# type = points:0.5
# If you want to plot a 4C track where you want to link
# the non-missing data (NaNs) together and only use the
# middle of the region instead of the region itself:
# Default is no.
# use_middle = yes
# By default the bedgraph is plotted at the base pair
# Resolution. This can lead to very large pdf/svg files
# If plotting a large regions.
# If you want to decrase the size of your file.
# You can either rasterize the bedgraph profile by using:
# rasterize = yes
# Or use a summary method on a given number of bin:
# The possible summary methods are given by pyBigWig:
# mean/average/stdev/dev/max/min/cov/coverage/sum
# summary_method = mean
# number_of_bins = 700
file_type = {}
    """.format(TRACK_TYPE)

    def __init__(self, properties_dict):
        super(BedGraphTrack, self).__init__(properties_dict)

        self.tbx = None
        # try to load a tabix file is available
        if self.properties['file'].endswith(".bgz"):
            import pysam
            # from the tabix file is not possible to know the
            # global min and max
            try:
                self.tbx = pysam.TabixFile(self.properties['file'])
            except IOError:
                self.interval_tree, ymin, ymax = file_to_intervaltree(self.properties['file'])
        # load the file as an interval tree
        else:
            self.interval_tree, ymin, ymax = file_to_intervaltree(self.properties['file'])

        self.num_fields = None
        self.set_properties_defaults()

    def set_properties_defaults(self):

        if 'color' not in self.properties:
            self.properties['color'] = DEFAULT_BEDGRAPH_COLOR

        if 'alpha' not in self.properties:
            self.properties['alpha'] = 1

        if 'negative color' not in self.properties:
            self.properties['negative color'] = self.properties['color']

        if 'nans to zeros' not in self.properties:
            self.properties['nans to zeros'] = False

        self.plot_type = 'fill'
        self.size = None

        if 'type' in self.properties:
            if self.properties['type'].find(":") > 0:
                self.plot_type, size = self.properties['type'].split(":")
                try:
                    self.size = float(size)
                except ValueError:
                    exit("Invalid value: 'type = {}' in section: {}\n"
                         "A number was expected and found '{}'".format(self.properties['type'],
                                                                       self.properties['section_name'],
                                                                       size))
            else:
                self.plot_type = self.properties['type']

        if self.plot_type not in ['line', 'points', 'fill']:
            exit("Invalid: 'type = {}' in section: {}\n".format(self.properties['type'],
                                                                self.properties['section_name']))

        if 'max_value' not in self.properties or self.properties['max_value'] == 'auto':
            self.properties['max_value'] = None

        if 'min_value' not in self.properties or self.properties['min_value'] == 'auto':
            self.properties['min_value'] = None

    def _get_row_data(self, row):
        """
        Returns the chrom, start, end and fields from either a tabix or a
        interval tree.
        Args:
            row: if tabix, the row comes from self.tbx.fetch otherwise
            comes from sorted(interval_tree[chrom] ...

        Returns:
            start, end, fields where values is a list

        """
        if self.tbx is not None:
            fields = row.split("\t")
            values = fields[3:]
            start = int(fields[1])
            end = int(fields[2])

        else:
            values = row.data
            start = row.begin
            end = row.end

        # set the num_fields value
        # it is expected that the number of fields per row
        # is equal. This value is used for regions not covered
        # in the file and that should be represented as nans
        if self.num_fields is None:
            self.num_fields = len(values)
        return start, end, values

    def get_scores(self, chrom_region, start_region, end_region, return_nans=True):
        """
        Retrieves the score (or scores or whatever fields are in a bedgraph like file) and the positions
        for a given region.
        In case there is no item in the region. It returns [], []
        Args:
            chrom_region:
            start_region:
            end_region:
        Returns:
            tuple:
                scores_list, post_list
        """
        score_list = []
        pos_list = []
        if self.tbx is not None:
            if chrom_region not in self.tbx.contigs:
                chrom_region_before = chrom_region
                chrom_region = self.change_chrom_names(chrom_region)
                if chrom_region not in self.tbx.contigs:
                    self.log.warning("*Warning*\nNeither "
                                     + chrom_region_before + " nor "
                                     + chrom_region + " exits as a "
                                     "chromosome name inside the bedgraph "
                                     "file. This will generate an empty "
                                     "track!!\n")
                    return score_list, pos_list

            chrom_region = self.check_chrom_str_bytes(self.tbx.contigs,
                                                      chrom_region)
            iterator = self.tbx.fetch(chrom_region, start_region, end_region)

        else:
            if chrom_region not in list(self.interval_tree):
                chrom_region_before = chrom_region
                chrom_region = self.change_chrom_names(chrom_region)
                if chrom_region not in list(self.interval_tree):
                    self.log.warning("*Warning*\nNeither "
                                     + chrom_region_before + " nor "
                                     + chrom_region + " exits as a "
                                     "chromosome name inside the bedgraph "
                                     "file. This will generate an empty "
                                     "track!!\n")
                    return score_list, pos_list
            chrom_region = self.check_chrom_str_bytes(self.interval_tree, chrom_region)
            iterator = iter(sorted(self.interval_tree[chrom_region][start_region - 10000:end_region + 10000]))

        prev_end = start_region
        for row in iterator:
            start, end, values = self._get_row_data(row)
            # if the region is not consecutive with respect to the previous
            # nan values are added.
            if return_nans and prev_end < start:
                score_list.append(np.repeat(np.nan, self.num_fields))
                pos_list.append((prev_end, start))
            prev_end = end
            score_list.append(values)
            pos_list.append((start, end))

        return score_list, pos_list

    def plot(self, ax, chrom_region, start_region, end_region):
        score_list, pos_list = self.get_scores(chrom_region, start_region, end_region)
        if pos_list == []:
            return
        score_list = [float(x[0]) for x in score_list]

        if self.properties.get('use middle', False) == 'yes':
            x_values = np.asarray([(t[0] + t[1]) / 2
                                   for i, t in enumerate(pos_list)
                                   if not np.isnan(score_list[i])],
                                  dtype=np.float)
            score_list = np.asarray([x for x in score_list if not np.isnan(x)],
                                    dtype=np.float)
        elif 'summary method' in self.properties:
            score_list, x_values = self.get_values_as_bigwig(score_list,
                                                             pos_list,
                                                             chrom_region,
                                                             start_region,
                                                             end_region)
        else:
            score_list, x_values = self.get_values_as_bdg(score_list,
                                                          pos_list)

        if 'extra' in self.properties and self.properties['extra'][0] == '4C':
            # draw a vertical line for each fragment region center
            ax.fill_between(pos_list, score_list, linewidth=0.1,
                            facecolor=self.properties['color'],
                            edgecolor='none', alpha=self.properties['alpha'])
            ax.vlines(pos_list, [0], score_list, color='olive', linewidth=0.5)
            ax.plot(pos_list, score_list, '-', color='slateblue', linewidth=0.7)
        else:
            plot_coverage(ax, x_values, score_list, self.plot_type, self.size,
                          self.properties['color'],
                          self.properties['negative color'],
                          self.properties['alpha'])

        ymax = self.properties['max_value']
        ymin = self.properties['min_value']
        plot_ymin, plot_ymax = ax.get_ylim()
        if ymax is None:
            ymax = plot_ymax
        if ymin is None:
            ymin = plot_ymin

        if 'orientation' in self.properties and self.properties['orientation'] == 'inverted':
            ax.set_ylim(ymax, ymin)
        else:
            ax.set_ylim(ymin, ymax)

        if self.properties.get('rasterize', False) == 'yes':
            ax.set_rasterized(True)

    def get_values_as_bigwig(self, score_list, pos_list, chrom_region,
                             start_region, end_region):
        if self.properties['summary method'] not in \
           ['mean', 'average', 'max', 'min', 'stdev',
           'dev', 'coverage', 'cov', 'sum']:
            self.log.warning("'summary method' value: {}"
                             " for bedgraph file {} is not valid"
                             "Using default bedgraph plot.")
            return self.get_values_as_bdg(score_list, pos_list)
        num_bins = 700
        if 'number of bins' in self.properties:
            try:
                num_bins = int(self.properties['number of bins'])
            except TypeError:
                num_bins = 700
                self.log.warning("'number of bins' value: {} for bedgraph file {} "
                                 "is not valid. Using default value (700)".format(self.properties['number of bins'],
                                                                                  self.properties['file']))
        import tempfile
        import os
        id, temp_bigwig_file = tempfile.mkstemp(suffix='.bw')
        bw = pyBigWig.open(temp_bigwig_file, 'w')
        bw.addHeader([(chrom_region, pos_list[-1][1])])
        bw.addEntries(np.repeat(chrom_region, len(pos_list)),
                      [p[0] for p in pos_list],
                      ends=[p[1] for p in pos_list],
                      values=score_list)
        bw.close()
        bw = pyBigWig.open(temp_bigwig_file)
        scores_per_bin = np.array(bw.stats(chrom_region, start_region,
                                           end_region, nBins=num_bins,
                                           type=self.properties['summary method'])).astype(float)
        os.remove(temp_bigwig_file)
        if self.properties['nans to zeros'] and np.any(np.isnan(scores_per_bin)):
            scores_per_bin[np.isnan(scores_per_bin)] = 0
        x_values = np.linspace(start_region, end_region, num_bins)

        return scores_per_bin, x_values

    def get_values_as_bdg(self, score_list, pos_list):
        # the following two lines will convert the score_list and the
        # tuples in pos list (where is item is tuple(start, end)
        # into an x value (pos_list) and a y value (score_list)
        # where x = start1, end1, star2, end2 ...
        # and y = score1, score1, score2, score2 ...

        # convert [1, 2, 3 ...] in [1, 1, 2, 2, 3, 3 ...]
        score_list = np.repeat(score_list, 2)
        # convert [(0, 10), (10, 20), (20, 30)] into [0, 10, 10, 20, 20, 30]
        x_values = np.asarray(sum(pos_list, tuple()), dtype=np.float)

        if self.properties['nans to zeros']:
            score_list[np.isnan(score_list)] = 0

        return score_list, x_values
