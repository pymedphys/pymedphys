#!/usr/bin/env python
# -*- encoding: utf-8

from __future__ import absolute_import, division, print_function

# unused import required to allow 'eval' of date filters
import datetime  # pylint: disable = unused-import
from bisect import bisect
from datetime import date  # pylint: disable = unused-import

import numpy as np
import pandas as pd

import matplotlib
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

try:
    import wx
except ImportError:
    import sys

    sys.path += [
        "/usr/lib/python2.7/dist-packages/wx-2.8-gtk2-unicode",
        "/usr/lib/python2.7/dist-packages",
    ]
    import wx

matplotlib.use("WXAgg")


# try to get nicer plotting styles
try:
    import seaborn

    seaborn.set()
except ImportError:
    try:
        from matplotlib import pyplot as plt

        plt.style.use("ggplot")
    except AttributeError:
        pass


class ListCtrlDataFrame(wx.ListCtrl):

    # TODO: we could do something more sophisticated to come
    # TODO: up with a reasonable column width...
    DEFAULT_COLUMN_WIDTH = 100
    TMP_SELECTION_COLUMN = "tmp_selection_column"

    def __init__(self, parent, df, status_bar_callback):
        wx.ListCtrl.__init__(
            self,
            parent,
            -1,
            style=wx.LC_REPORT
            | wx.LC_VIRTUAL
            | wx.LC_HRULES
            | wx.LC_VRULES
            | wx.LB_MULTIPLE,
        )
        self.status_bar_callback = status_bar_callback

        self.df_orig = df
        self.original_columns = self.df_orig.columns[:]
        if isinstance(self.original_columns, (pd.RangeIndex, pd.Int64Index)):
            # RangeIndex is not supported by self._update_columns
            self.original_columns = pd.Index([str(i) for i in self.original_columns])
        self.current_columns = self.df_orig.columns[:]

        self.sort_by_column = None

        self._reset_mask()

        # prepare attribute for alternating colors of rows
        self.attr_light_blue = wx.ListItemAttr()
        self.attr_light_blue.SetBackgroundColour("#D6EBFF")

        self.Bind(wx.EVT_LIST_COL_CLICK, self._on_col_click)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_right_click)

        self.df = pd.DataFrame({})  # init empty to force initial update
        self._update_rows()
        self._update_columns(self.original_columns)

    def _reset_mask(self):
        # self.mask = [True] * self.df_orig.shape[0]
        self.mask = pd.Series([True] * self.df_orig.shape[0], index=self.df_orig.index)

    def _update_columns(self, columns):
        self.ClearAll()
        for i, col in enumerate(columns):
            self.InsertColumn(i, col)
            self.SetColumnWidth(i, self.DEFAULT_COLUMN_WIDTH)
        # Note that we have to reset the count as well because ClearAll()
        # not only deletes columns but also the count...
        self.SetItemCount(len(self.df))

    def set_columns(self, columns_to_use):
        """
        External interface to set the column projections.
        """
        self.current_columns = columns_to_use
        self._update_rows()
        self._update_columns(columns_to_use)

    def _update_rows(self):
        old_len = len(self.df)
        self.df = self.df_orig.loc[self.mask.values, self.current_columns]
        new_len = len(self.df)
        if old_len != new_len:
            self.SetItemCount(new_len)
            self.status_bar_callback(0, "Number of rows: {}".format(new_len))

    def apply_filter(self, conditions):
        """
        External interface to set a filter.
        """
        old_mask = self.mask.copy()

        if len(conditions) == 0:
            self._reset_mask()

        else:
            self._reset_mask()  # set all to True for destructive conjunction

            no_error = True
            for column, condition in conditions:
                if condition.strip() == "":
                    continue
                condition = condition.replace("_", "self.df_orig['{}']".format(column))
                print("Evaluating condition:", condition)
                try:
                    tmp_mask = eval(condition)
                    if isinstance(tmp_mask, pd.Series) and tmp_mask.dtype == np.bool:
                        self.mask &= tmp_mask
                except Exception as e:
                    print("Failed with:", e)
                    no_error = False
                    self.status_bar_callback(
                        1, "Evaluating '{}' failed with: {}".format(condition, e)
                    )

            if no_error:
                self.status_bar_callback(1, "")

        has_changed = any(old_mask != self.mask)
        if has_changed:
            self._update_rows()

        return len(self.df), has_changed

    def get_selected_items(self):
        """
        Gets the selected items for the list control.
        Selection is returned as a list of selected indices,
        low to high.
        """
        selection = []
        current = -1  # start at -1 to get the first selected item
        while True:
            next = self.GetNextItem(current, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if next == -1:
                return selection
            else:
                selection.append(next)
                current = next

    def get_filtered_df(self):
        return self.df_orig.loc[self.mask, :]

    def _on_col_click(self, event):
        """
        Sort data frame by selected column.
        """
        # get currently selected items
        selected = self.get_selected_items()

        # append a temporary column to store the currently selected items
        self.df[self.TMP_SELECTION_COLUMN] = False
        self.df.iloc[selected, -1] = True

        # get column name to use for sorting
        col = event.GetColumn()

        # determine if ascending or descending
        if self.sort_by_column is None or self.sort_by_column[0] != col:
            ascending = True
        else:
            ascending = not self.sort_by_column[1]

        # store sort column and sort direction
        self.sort_by_column = (col, ascending)

        try:
            # pandas 0.17
            self.df.sort_values(self.df.columns[col], inplace=True, ascending=ascending)
        except AttributeError:
            # pandas 0.16 compatibility
            self.df.sort(self.df.columns[col], inplace=True, ascending=ascending)

        # deselect all previously selected
        for i in selected:
            self.Select(i, on=False)

        # determine indices of selection after sorting
        selected_bool = self.df.iloc[:, -1] == True
        selected = self.df.reset_index().index[selected_bool]

        # select corresponding rows
        for i in selected:
            self.Select(i, on=True)

        # delete temporary column
        del self.df[self.TMP_SELECTION_COLUMN]

    def _on_right_click(self, event):
        """
        Copies a cell into clipboard on right click. Unfortunately,
        determining the clicked column is not straightforward. This
        appraoch is inspired by the TextEditMixin in:
        /usr/lib/python2.7/dist-packages/wx-2.8-gtk2-unicode/wx/lib/mixins/listctrl.py
        More references:
        - http://wxpython-users.1045709.n5.nabble.com/Getting-row-col-of-selected-cell-in-ListCtrl-td2360831.html
        - https://groups.google.com/forum/#!topic/wxpython-users/7BNl9TA5Y5U
        - https://groups.google.com/forum/#!topic/wxpython-users/wyayJIARG8c
        """
        if self.HitTest(event.GetPosition()) != wx.NOT_FOUND:
            x, y = event.GetPosition()
            row, flags = self.HitTest((x, y))

            col_locs = [0]
            loc = 0
            for n in range(self.GetColumnCount()):
                loc = loc + self.GetColumnWidth(n)
                col_locs.append(loc)

            scroll_pos = self.GetScrollPos(wx.HORIZONTAL)
            # this is crucial step to get the scroll pixel units
            unit_x, unit_y = self.GetMainWindow().GetScrollPixelsPerUnit()

            col = bisect(col_locs, x + scroll_pos * unit_x) - 1

            value = self.df.iloc[row, col]
            # print(row, col, scroll_pos, value)

            clipdata = wx.TextDataObject()
            clipdata.SetText(str(value))
            wx.TheClipboard.Open()
            wx.TheClipboard.SetData(clipdata)
            wx.TheClipboard.Close()

    def OnGetItemText(self, item, col):
        """
        Implements the item getter for a "virtual" ListCtrl.
        """
        value = self.df.iloc[item, col]
        # print("retrieving %d %d %s" % (item, col, value))
        return str(value)

    def OnGetItemAttr(self, item):
        """
        Implements the attribute getter for a "virtual" ListCtrl.
        """
        if item % 2 == 0:
            return self.attr_light_blue
        else:
            return None


class DataframePanel(wx.Panel):
    """
    Panel providing the main data frame table view.
    """

    def __init__(self, parent, df, status_bar_callback):
        wx.Panel.__init__(self, parent)

        self.df_list_ctrl = ListCtrlDataFrame(self, df, status_bar_callback)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.df_list_ctrl, 1, wx.ALL | wx.EXPAND | wx.GROW, 5)
        self.SetSizer(sizer)
        self.Show()


class ListBoxDraggable(wx.ListBox):
    """
    Helper class to provide ListBox with extended behavior.
    """

    def __init__(self, parent, size, data, *args, **kwargs):

        wx.ListBox.__init__(self, parent, size, **kwargs)

        if isinstance(data, (pd.RangeIndex, pd.Int64Index)):
            # RangeIndex is not supported by self._update_columns
            data = pd.Index([str(i) for i in data])
        self.data = data

        self.InsertItems(self.data, 0)

        self.Bind(wx.EVT_LISTBOX, self.on_selection_changed)

        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)

        self.Bind(wx.EVT_RIGHT_DOWN, self.on_right_down)
        self.Bind(wx.EVT_RIGHT_UP, self.on_right_up)
        self.Bind(wx.EVT_MOTION, self.on_move)

        self.index_iter = range(len(self.data))

        self.selected_items = [True] * len(self.data)
        self.index_mapping = list(range(len(self.data)))

        self.drag_start_index = None

        self.update_selection()
        self.SetFocus()

    def on_left_down(self, event):
        if self.HitTest(event.GetPosition()) != wx.NOT_FOUND:
            index = self.HitTest(event.GetPosition())
            self.selected_items[index] = not self.selected_items[index]
            # doesn't really work to update selection direclty (focus issues)
            # instead we wait for the EVT_LISTBOX event and fix the selection
            # there...
            # self.update_selection()
            # TODO: we could probably use wx.CallAfter
        event.Skip()

    def update_selection(self):
        # self.SetFocus()
        # print(self.selected_items)
        for i in self.index_iter:
            if self.IsSelected(i) and not self.selected_items[i]:
                # print("Deselecting", i)
                self.Deselect(i)
            elif not self.IsSelected(i) and self.selected_items[i]:
                # print("Selecting", i)
                self.Select(i)

    def on_selection_changed(self, evt):
        self.update_selection()
        evt.Skip()

    def on_right_down(self, event):
        if self.HitTest(event.GetPosition()) != wx.NOT_FOUND:
            index = self.HitTest(event.GetPosition())
            self.drag_start_index = index

    def on_right_up(self, event):
        self.drag_start_index = None
        event.Skip()

    def on_move(self, event):
        if self.drag_start_index is not None:
            if self.HitTest(event.GetPosition()) != wx.NOT_FOUND:
                index = self.HitTest(event.GetPosition())
                if self.drag_start_index != index:
                    self.swap(self.drag_start_index, index)
                    self.drag_start_index = index

    def swap(self, i, j):
        self.index_mapping[i], self.index_mapping[j] = (
            self.index_mapping[j],
            self.index_mapping[i],
        )
        self.SetString(i, self.data[self.index_mapping[i]])
        self.SetString(j, self.data[self.index_mapping[j]])
        self.selected_items[i], self.selected_items[j] = (
            self.selected_items[j],
            self.selected_items[i],
        )
        # self.update_selection()
        # print("Updated mapping:", self.index_mapping)
        new_event = wx.PyCommandEvent(wx.EVT_LISTBOX.typeId, self.GetId())
        self.GetEventHandler().ProcessEvent(new_event)

    def get_selected_data(self):
        selected = []
        for i, col in enumerate(self.data):
            if self.IsSelected(i):
                index = self.index_mapping[i]
                value = self.data[index]
                selected.append(value)
        # print("Selected data:", selected)
        return selected


class ColumnSelectionPanel(wx.Panel):
    """
    Panel for selecting and re-arranging columns.
    """

    def __init__(self, parent, columns, df_list_ctrl):
        wx.Panel.__init__(self, parent)

        self.columns = columns
        self.df_list_ctrl = df_list_ctrl

        self.list_box = ListBoxDraggable(self, -1, columns, style=wx.LB_EXTENDED)
        self.Bind(wx.EVT_LISTBOX, self.update_selected_columns)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list_box, 1, wx.ALL | wx.EXPAND | wx.GROW, 5)
        self.SetSizer(sizer)
        self.list_box.SetFocus()

    def update_selected_columns(self, evt):
        selected = self.list_box.get_selected_data()
        self.df_list_ctrl.set_columns(selected)


class FilterPanel(wx.Panel):
    """
    Panel for defining filter expressions.
    """

    def __init__(self, parent, columns, df_list_ctrl, change_callback):
        wx.Panel.__init__(self, parent)

        columns_with_neutral_selection = [""] + list(columns)
        self.columns = columns
        self.df_list_ctrl = df_list_ctrl
        self.change_callback = change_callback

        self.num_filters = 10

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.combo_boxes = []
        self.text_controls = []

        for i in range(self.num_filters):
            combo_box = wx.ComboBox(
                self, choices=columns_with_neutral_selection, style=wx.CB_READONLY
            )
            text_ctrl = wx.TextCtrl(self, wx.ID_ANY, "")

            self.Bind(wx.EVT_COMBOBOX, self.on_combo_box_select)
            self.Bind(wx.EVT_TEXT, self.on_text_change)

            row_sizer = wx.BoxSizer(wx.HORIZONTAL)
            row_sizer.Add(combo_box, 0, wx.ALL, 5)
            row_sizer.Add(text_ctrl, 1, wx.ALL | wx.EXPAND | wx.ALIGN_RIGHT, 5)

            self.combo_boxes.append(combo_box)
            self.text_controls.append(text_ctrl)
            self.main_sizer.Add(row_sizer, 0, wx.EXPAND)

        self.SetSizer(self.main_sizer)

    def on_combo_box_select(self, event):
        self.update_conditions()

    def on_text_change(self, event):
        self.update_conditions()

    def update_conditions(self):
        # print("Updating conditions")
        conditions = []
        for i in range(self.num_filters):
            column_index = self.combo_boxes[i].GetSelection()
            condition = self.text_controls[i].GetValue()
            if column_index != wx.NOT_FOUND and column_index != 0:
                # since we have added a dummy column for "deselect", we have to subtract one
                column = self.columns[column_index - 1]
                conditions += [(column, condition)]
        num_matching, has_changed = self.df_list_ctrl.apply_filter(conditions)
        if has_changed:
            self.change_callback()
        # print("Num matching:", num_matching)


class HistogramPlot(wx.Panel):
    """
    Panel providing a histogram plot.
    """

    def __init__(self, parent, columns, df_list_ctrl):
        wx.Panel.__init__(self, parent)

        columns_with_neutral_selection = [""] + list(columns)
        self.columns = columns
        self.df_list_ctrl = df_list_ctrl

        self.figure = Figure(facecolor="white", figsize=(1, 1))
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self, -1, self.figure)

        chart_toolbar = NavigationToolbar2Wx(self.canvas)

        self.combo_box1 = wx.ComboBox(
            self, choices=columns_with_neutral_selection, style=wx.CB_READONLY
        )

        self.Bind(wx.EVT_COMBOBOX, self.on_combo_box_select)

        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        row_sizer.Add(self.combo_box1, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        row_sizer.Add(chart_toolbar, 0, wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, flag=wx.EXPAND, border=5)
        sizer.Add(row_sizer)
        self.SetSizer(sizer)

    def on_combo_box_select(self, event):
        self.redraw()

    def redraw(self):
        column_index1 = self.combo_box1.GetSelection()
        if column_index1 != wx.NOT_FOUND and column_index1 != 0:
            # subtract one to remove the neutral selection index
            column_index1 -= 1

            df = self.df_list_ctrl.get_filtered_df()

            if len(df) > 0:
                self.axes.clear()

                column = df.iloc[:, column_index1]
                is_string_col = column.dtype == np.object and isinstance(
                    column.values[0], str
                )
                if is_string_col:
                    value_counts = column.value_counts().sort_index()
                    value_counts.plot(kind="bar", ax=self.axes)
                else:
                    self.axes.hist(column.values, bins=100)

                self.canvas.draw()


class ScatterPlot(wx.Panel):
    """
    Panel providing a scatter plot.
    """

    def __init__(self, parent, columns, df_list_ctrl):
        wx.Panel.__init__(self, parent)

        columns_with_neutral_selection = [""] + list(columns)
        self.columns = columns
        self.df_list_ctrl = df_list_ctrl

        self.figure = Figure(facecolor="white", figsize=(1, 1))
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self, -1, self.figure)

        chart_toolbar = NavigationToolbar2Wx(self.canvas)

        self.combo_box1 = wx.ComboBox(
            self, choices=columns_with_neutral_selection, style=wx.CB_READONLY
        )
        self.combo_box2 = wx.ComboBox(
            self, choices=columns_with_neutral_selection, style=wx.CB_READONLY
        )

        self.Bind(wx.EVT_COMBOBOX, self.on_combo_box_select)

        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        row_sizer.Add(self.combo_box1, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        row_sizer.Add(self.combo_box2, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        row_sizer.Add(chart_toolbar, 0, wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, flag=wx.EXPAND, border=5)
        sizer.Add(row_sizer)
        self.SetSizer(sizer)

    def on_combo_box_select(self, event):
        self.redraw()

    def redraw(self):
        column_index1 = self.combo_box1.GetSelection()
        column_index2 = self.combo_box2.GetSelection()
        if (
            column_index1 != wx.NOT_FOUND
            and column_index1 != 0
            and column_index2 != wx.NOT_FOUND
            and column_index2 != 0
        ):
            # subtract one to remove the neutral selection index
            column_index1 -= 1
            column_index2 -= 1
            df = self.df_list_ctrl.get_filtered_df()

            # It looks like using pandas dataframe.plot causes something weird to
            # crash in wx internally. Therefore we use plain axes.plot functionality.
            # column_name1 = self.columns[column_index1]
            # column_name2 = self.columns[column_index2]
            # df.plot(kind='scatter', x=column_name1, y=column_name2)

            if len(df) > 0:
                self.axes.clear()
                self.axes.plot(
                    df.iloc[:, column_index1].values,
                    df.iloc[:, column_index2].values,
                    "o",
                    clip_on=False,
                )

                self.canvas.draw()


class MainFrame(wx.Frame):
    """
    The main GUI window.
    """

    def __init__(self, df):
        wx.Frame.__init__(self, None, -1, "Pandas DataFrame GUI")

        # Here we create a panel and a notebook on the panel
        p = wx.Panel(self)
        nb = wx.Notebook(p)
        self.nb = nb

        columns = df.columns[:]
        if isinstance(columns, (pd.RangeIndex, pd.Int64Index)):
            # RangeIndex is not supported
            columns = pd.Index([str(i) for i in columns])
        self.CreateStatusBar(2, style=0)
        self.SetStatusWidths([200, -1])

        # create the page windows as children of the notebook
        self.page1 = DataframePanel(nb, df, self.status_bar_callback)
        self.page2 = ColumnSelectionPanel(nb, columns, self.page1.df_list_ctrl)
        self.page3 = FilterPanel(
            nb, columns, self.page1.df_list_ctrl, self.selection_change_callback
        )
        self.page4 = HistogramPlot(nb, columns, self.page1.df_list_ctrl)
        self.page5 = ScatterPlot(nb, columns, self.page1.df_list_ctrl)

        # add the pages to the notebook with the label to show on the tab
        nb.AddPage(self.page1, "Data Frame")
        nb.AddPage(self.page2, "Columns")
        nb.AddPage(self.page3, "Filters")
        nb.AddPage(self.page4, "Histogram")
        nb.AddPage(self.page5, "Scatter Plot")

        nb.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)

        # finally, put the notebook in a sizer for the panel to manage
        # the layout
        sizer = wx.BoxSizer()
        sizer.Add(nb, 1, wx.EXPAND)
        p.SetSizer(sizer)

        self.SetSize((800, 600))
        self.Center()

    def on_tab_change(self, event):
        self.page2.list_box.SetFocus()
        page_to_select = event.GetSelection()
        wx.CallAfter(self.fix_focus, page_to_select)
        event.Skip(True)

    def fix_focus(self, page_to_select):
        page = self.nb.GetPage(page_to_select)
        page.SetFocus()
        if isinstance(page, DataframePanel):
            self.page1.df_list_ctrl.SetFocus()
        elif isinstance(page, ColumnSelectionPanel):
            self.page2.list_box.SetFocus()

    def status_bar_callback(self, i, new_text):
        self.SetStatusText(new_text, i)

    def selection_change_callback(self):
        self.page4.redraw()
        self.page5.redraw()


def show(df):
    """
    The main function to start the data frame GUI.
    """

    app = wx.App(False)
    frame = MainFrame(df)
    frame.Show()
    app.MainLoop()
