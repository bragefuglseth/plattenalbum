#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# mpdevil - MPD Client.
# Copyright 2020 Martin Wagner
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA

import gi #python-gobject  dev-python/pygobject:3[${PYTHON_USEDEP}]
gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, Gio, Gdk, GdkPixbuf, Pango, GObject, GLib, Notify
from mpd import MPDClient
import requests #dev-python/requests
from bs4 import BeautifulSoup, Comment #, NavigableString #dev-python/beautifulsoup
import threading
import locale
import gettext
import datetime
import os
import sys

DATADIR = '@datadir@'
NAME = 'mpdevil'
VERSION = '@version@'
PACKAGE = NAME.lower()

try:
	locale.setlocale(locale.LC_ALL, '')
	locale.bindtextdomain(PACKAGE, '@datadir@/locale')
	gettext.bindtextdomain(PACKAGE, '@datadir@/locale')
	gettext.textdomain(PACKAGE)
	gettext.install(PACKAGE, localedir='@datadir@/locale')
except locale.Error:
	print('  cannot use system locale.')
	locale.setlocale(locale.LC_ALL, 'C')
	gettext.textdomain(PACKAGE)
	gettext.install(PACKAGE, localedir='@datadir@/locale')

class IntEntry(Gtk.SpinButton):
	def __init__(self, default, lower, upper):
		Gtk.SpinButton.__init__(self)
		adj = Gtk.Adjustment(value=default, lower=lower, upper=upper, step_increment=1)
		self.set_adjustment(adj)

	def get_int(self):
		return int(self.get_value())

	def set_int(self, value):
		self.set_value(value)

class Cover(object):
	def __init__(self, client, lib_path, song_file):
		self.client=client
		self.lib_path=lib_path
		self.path=None
		if not song_file == None:
			head_tail=os.path.split(song_file)
			path=(self.lib_path+"/"+head_tail[0]+"/")
			if os.path.exists(path):
				filelist=[file for file in os.listdir(path) if file.endswith('.jpg') or file.endswith('.png') or file.endswith('.gif')]
				if not filelist == []:
					self.path=(path+filelist[0])

	def get_pixbuf(self, size):
		if self.path == None:
			self.path = Gtk.IconTheme.get_default().lookup_icon("mpdevil", size, Gtk.IconLookupFlags.FORCE_SVG).get_filename() #fallback cover
		return GdkPixbuf.Pixbuf.new_from_file_at_size(self.path, size, size)

class Client(MPDClient):
	def __init__(self, settings):
		MPDClient.__init__(self)
		self.settings = settings
		self.song_to_delete=""
		self.settings.connect("changed::active-profile", self.on_settings_changed)

	def try_connect_default(self):
		active=self.settings.get_int("active-profile")
		try:
			self.connect(self.settings.get_value("hosts")[active], self.settings.get_value("ports")[active])
			if self.settings.get_value("passwords")[active] == "":
				self.password(None)
			else:
				self.password(self.settings.get_value("passwords")[active])
		except:
			pass

	def connected(self):
		try:
			self.ping()
			return True
		except:
			return False

	def album_to_playlist(self, album, artist, year, append, force=False):
		if append:
			songs=self.find("album", album, "date", year, self.settings.get_artist_type(), artist)
			if not songs == []:
				for song in songs:
					self.add(song["file"])
		else:
			if self.settings.get_boolean("add-album") and not force and not self.status()["state"] == "stop":
				status=self.status()
				self.moveid(status["songid"], 0)
				self.song_to_delete=self.playlistinfo()[0]["file"]
				try:
					self.delete((1,)) # delete all songs, but the first. #bad song index possible
				except:
					pass
				songs=self.find("album", album, "date", year, self.settings.get_artist_type(), artist)
				if not songs == []:
					for song in songs:
						if not song["file"] == self.song_to_delete:
							self.add(song["file"])
						else:
							self.move(0, (len(self.playlist())-1))
							self.song_to_delete=""
			else:
				songs=self.find("album", album, "date", year, self.settings.get_artist_type(), artist)
				if not songs == []:
					self.stop()
					self.clear()
					for song in songs:
						self.add(song["file"])
					self.play()

	def on_settings_changed(self, *args):
		self.disconnect()

class MpdEventEmitter(GObject.Object):
	def __init__(self, settings):
		super().__init__()
		self.client=Client(settings)
		GLib.timeout_add(100, self.watch)
		self.connected=True

	def watch(self, *args):
		try:
			a=self.client.noidle()
			for i in a:
				self.emit(i)
		except:
			pass
		try:
			self.client.send_idle()
		except:
			self.client.try_connect_default()
			if self.client.connected():
				self.emit("disconnected")
				self.emit("reconnected")
				self.connected=True
			elif self.connected:
				self.emit("disconnected")
				self.connected=False
		return True

	@GObject.Signal
	def database(self):
		pass

	@GObject.Signal
	def update(self):
		pass

	@GObject.Signal
	def stored_playlist(self):
		pass

	@GObject.Signal
	def playlist(self):
		pass

	@GObject.Signal
	def player(self):
		pass

	@GObject.Signal
	def mixer(self):
		pass

	@GObject.Signal
	def output(self):
		pass

	@GObject.Signal
	def options(self):
		pass

	@GObject.Signal
	def sticker(self):
		pass

	@GObject.Signal
	def subscription(self):
		pass

	@GObject.Signal
	def message(self):
		pass

	@GObject.Signal
	def disconnected(self):
		pass

	@GObject.Signal
	def reconnected(self):
		pass

class Settings(Gio.Settings):
	BASE_KEY = "org.mpdevil"
	def __init__(self):
		super().__init__(schema=self.BASE_KEY)
		if len(self.get_value("profiles")) < (self.get_int("active-profile")+1):
			self.set_int("active-profile", 0)

	def array_append(self, vtype, key, value): #append to Gio.Settings (self.settings) array
		array=self.get_value(key).unpack()
		array.append(value)
		self.set_value(key, GLib.Variant(vtype, array))

	def array_delete(self, vtype, key, pos): #delete entry of Gio.Settings (self.settings) array
		array=self.get_value(key).unpack()
		array.pop(pos)
		self.set_value(key, GLib.Variant(vtype, array))

	def array_modify(self, vtype, key, pos, value): #modify entry of Gio.Settings (self.settings) array
		array=self.get_value(key).unpack()
		array[pos]=value
		self.set_value(key, GLib.Variant(vtype, array))

	def get_gtk_icon_size(self, key):
		icon_size=self.get_int(key)
		if icon_size == 16:
			return Gtk.IconSize.BUTTON
		elif icon_size == 24:
			return Gtk.IconSize.LARGE_TOOLBAR
		elif icon_size == 32:
			return Gtk.IconSize.DND
		elif icon_size == 48:
			return Gtk.IconSize.DIALOG
		else:
#			return Gtk.IconSize.INVALID
			raise ValueError

	def get_artist_type(self):
		if self.get_boolean("show-all-artists"):
			return ("artist")
		else:
			return ("albumartist")

class AlbumDialog(Gtk.Dialog):
	def __init__(self, parent, client, settings, album, artist, year):
		Gtk.Dialog.__init__(self, title=(artist+" - "+album+" ("+year+")"), transient_for=parent)
		self.add_buttons(Gtk.STOCK_ADD, Gtk.ResponseType.ACCEPT, Gtk.STOCK_MEDIA_PLAY, Gtk.ResponseType.YES, Gtk.STOCK_OPEN, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
		self.set_default_size(800, 600)

		#adding vars
		self.client=client
		self.settings=settings

		#scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

		#Store
		#(track, title, artist, duration, file)
		self.store = Gtk.ListStore(str, str, str, str, str)

		#TreeView
		self.treeview = Gtk.TreeView(model=self.store)
		self.treeview.set_search_column(-1)
		self.treeview.columns_autosize()

		self.selection = self.treeview.get_selection()
		self.selection.set_mode(Gtk.SelectionMode.SINGLE)

		#Column
		renderer_text = Gtk.CellRendererText()

		self.column_track = Gtk.TreeViewColumn(_("No"), renderer_text, text=0)
		self.column_track.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_track.set_property("resizable", False)
		self.treeview.append_column(self.column_track)

		self.column_title = Gtk.TreeViewColumn(_("Title"), renderer_text, text=1)
		self.column_title.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_title.set_property("resizable", False)
		self.treeview.append_column(self.column_title)

		self.column_artist = Gtk.TreeViewColumn(_("Artist"), renderer_text, text=2)
		self.column_artist.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_artist.set_property("resizable", False)
		self.treeview.append_column(self.column_artist)

		self.column_time = Gtk.TreeViewColumn(_("Length"), renderer_text, text=3)
		self.column_time.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_time.set_property("resizable", False)
		self.treeview.append_column(self.column_time)

		self.populate_treeview(album, artist, year)

		#connect
		self.title_activated=self.treeview.connect("row-activated", self.on_row_activated)

		#packing
		scroll.add(self.treeview)
		self.vbox.pack_start(scroll, True, True, 0) #vbox default widget of dialogs
		self.vbox.set_spacing(6)
		self.show_all()

		#selection workaround
		self.selection.unselect_all()
		self.title_change=self.selection.connect("changed", self.on_selection_change)

	def on_row_activated(self, widget, path, view_column):
		treeiter=self.store.get_iter(path)
		selected_title=self.store.get_value(treeiter, 4)
		self.client.clear()
		self.client.add(selected_title)
		self.client.play()

	def on_selection_change(self, widget):
		treeiter=widget.get_selected()[1]
		if not treeiter == None:
			selected_title=self.store.get_value(treeiter, 4)
			self.client.add(selected_title)

	def populate_treeview(self, album, artist, year):
		songs=self.client.find("album", album, "date", year, self.settings.get_artist_type(), artist)
		if not songs == []:
			for song in songs:
				try:
					title=song["title"]
				except:
					title=_("Unknown Title")
				try:
					artist=song["artist"]
				except:
					artist=_("Unknown Artist")
				try:
					track=song["track"].zfill(2)
				except:
					track="00"
				try:
					dura=float(song["duration"])
				except:
					dura=0.0
				duration=str(datetime.timedelta(seconds=int(dura)))
				self.store.append([track, title, artist, duration, song["file"]] )

class GenreSelect(Gtk.Box):
	def __init__(self, client, settings, emitter):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

		#adding vars
		self.client=client
		self.settings=settings
		self.emitter=emitter

		self.combo=Gtk.ComboBoxText()

		#connect
		self.combo_changed=self.combo.connect("changed", self.on_combo_changed)
		self.update_signal=self.emitter.connect("update", self.refresh)

		self.pack_start(self.combo, True, True, 0)

	@GObject.Signal
	def changed(self):
		self.emitter.handler_block(self.update_signal)
		self.emitter.emit("update")
		self.emitter.handler_unblock(self.update_signal)

	def deactivate(self):
		self.combo.set_active(0)

	def refresh(self, *args):
		self.combo.handler_block(self.combo_changed)
		self.combo.remove_all()
		self.combo.append_text(_("all genres"))
		for genre in self.client.list("genre"):
			self.combo.append_text(genre)
		self.combo.set_active(0)
		self.combo.handler_unblock(self.combo_changed)

	def get_value(self):
		if self.combo.get_active() == 0:
			return None
		else:
			return self.combo.get_active_text()

	def on_combo_changed(self, *args):
		self.emit("changed")

class ArtistView(Gtk.ScrolledWindow):
	def __init__(self, client, settings, emitter, genre_select):
		Gtk.ScrolledWindow.__init__(self)
		self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

		#adding vars
		self.client=client
		self.settings=settings
		self.emitter=emitter
		self.genre_select=genre_select

		#artistStore
		#(name)
		self.store = Gtk.ListStore(str)
		self.store.set_sort_column_id(0, Gtk.SortType.ASCENDING)

		#TreeView
		self.treeview = Gtk.TreeView(model=self.store)
		self.treeview.set_search_column(-1)
		self.treeview.columns_autosize()

		#artistSelection
		self.selection = self.treeview.get_selection()
		self.selection.set_mode(Gtk.SelectionMode.MULTIPLE)

		#Old Name Column
		renderer_text = Gtk.CellRendererText()
		self.column_name = Gtk.TreeViewColumn("", renderer_text, text=0)
		self.column_name.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_name.set_property("resizable", False)
		self.column_name.set_sort_column_id(0)
		self.treeview.append_column(self.column_name)

		#connect
		self.treeview.connect("enter-notify-event", self.on_enter_event)
		self.settings.connect("changed::show-all-artists", self.refresh)
		self.update_signal=self.emitter.connect("update", self.refresh)

		self.add(self.treeview)

	def clear(self):
		self.store.clear()

	def refresh(self, *args):
		self.selection.set_mode(Gtk.SelectionMode.NONE)
		self.clear()
		if self.settings.get_artist_type() == "albumartist":
			self.column_name.set_title(_("Album Artist"))
		else:
			self.column_name.set_title(_("Artist"))
		genre=self.genre_select.get_value()
		if genre == None:
			artists=self.client.list(self.settings.get_artist_type())
		else:
			artists=self.client.list(self.settings.get_artist_type(), "genre", genre)
		for artist in artists:
			self.store.append([artist])
		self.selection.set_mode(Gtk.SelectionMode.MULTIPLE)

	def get_selected_artists(self):
		paths=self.selection.get_selected_rows()[1]
		artists=[]
		for path in paths:
			treeiter = self.store.get_iter(path)
			if not treeiter == None:
				selected_artist=self.store.get_value(treeiter, 0)
				artists.append(selected_artist)
		return artists

	def on_enter_event(self, widget, event):
		self.treeview.grab_focus()

class AlbumIconView(Gtk.IconView):
	def __init__(self, client, settings, genre_select, window):
		Gtk.IconView.__init__(self)

		#adding vars
		self.settings=settings
		self.client=client
		self.genre_select=genre_select
		self.window=window
		self.stop_flag=True

		#cover, display_label, tooltip(titles), album, year, artist
		self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, str)
		self.sort_settings()

		#iconview
		self.set_model(self.store)
		self.set_pixbuf_column(0)
		self.set_text_column(1)
		self.set_item_width(0)
		self.tooltip_settings()

		#connect
		self.album_change=self.connect("selection-changed", self.on_album_selection_change)
		self.album_item_activated=self.connect("item-activated", self.on_album_item_activated)
		self.connect("button-press-event", self.on_album_view_button_press_event)
		self.settings.connect("changed::show-album-view-tooltips", self.tooltip_settings)
		self.settings.connect("changed::sort-albums-by-year", self.sort_settings)
		self.connect("motion-notify-event", self.on_move_event)

	@GObject.Signal
	def stopped(self):
		pass

	def tooltip_settings(self, *args):
		if self.settings.get_boolean("show-album-view-tooltips"):
			self.set_tooltip_column(2)
		else:
			self.set_tooltip_column(-1)

	def sort_settings(self, *args):
		if self.settings.get_boolean("sort-albums-by-year"):
			self.store.set_sort_column_id(4, Gtk.SortType.ASCENDING)
		else:
			self.store.set_sort_column_id(1, Gtk.SortType.ASCENDING)

	def gen_tooltip(self, album, artist, year):
		songs=self.client.find("album", album, "date", year, self.settings.get_artist_type(), artist)
		length=float(0)
		for song in songs:
			try:
				dura=float(song["duration"])
			except:
				dura=0.0
			length=length+dura
		length_human_readable=str(datetime.timedelta(seconds=int(length)))
		tooltip=(_("%(total_tracks)i titles (%(total_length)s)") % {"total_tracks": len(songs), "total_length": length_human_readable})
		return tooltip

	def populate(self, artists):
		self.stop_flag=False
		size=self.settings.get_int("album-cover")
		albums=[]
		genre=self.genre_select.get_value()
		for artist in artists:
			if genre == None:
				album_candidates=self.client.list("album", self.settings.get_artist_type(), artist)
			else:
				album_candidates=self.client.list("album", self.settings.get_artist_type(), artist, "genre", genre)
			for album in album_candidates:
				albums.append({"artist": artist, "album": album, "year": self.client.list("date", "album", album, self.settings.get_artist_type(), artist)[0]})
		if self.settings.get_boolean("sort-albums-by-year"):
			albums = sorted(albums, key=lambda k: k['year'])
		else:
			albums = sorted(albums, key=lambda k: k['album'])
		for album in albums:
			if self.client.connected() and not self.stop_flag: #self.get_visible() and self.client.connected() and 
				songs=self.client.find("album", album["album"], "date", album["year"], self.settings.get_artist_type(), album["artist"])
				if songs == []:
					song_file=None
				else:
					song_file=songs[0]["file"]
				cover=Cover(client=self.client, lib_path=self.settings.get_value("paths")[self.settings.get_int("active-profile")], song_file=song_file)
				img=cover.get_pixbuf(size)
				if album["year"] == "":
					self.store.append([img, album["album"], self.gen_tooltip(album["album"], album["artist"], album["year"]), album["album"], album["year"], album["artist"]])
				else:
					self.store.append([img, album["album"]+" ("+album["year"]+")", self.gen_tooltip(album["album"], album["artist"], album["year"]), album["album"], album["year"], album["artist"]])
				while Gtk.events_pending():
					Gtk.main_iteration_do(True)
			else:
				self.store.clear()
				self.emit("stopped")
				break
		self.stop_flag=True

	def scroll_to_selected_album(self):
		songid=self.client.status()["songid"]
		song=self.client.playlistid(songid)[0]
		self.handler_block(self.album_change)
		self.unselect_all()
		row_num=len(self.store)
		for i in range(0, row_num):
			path=Gtk.TreePath(i)
			treeiter = self.store.get_iter(path)
			if self.store.get_value(treeiter, 3) == song["album"]:
				self.set_cursor(path, None, False)
				self.select_path(path)
				self.scroll_to_path(path, True, 0, 0)
				break
		self.handler_unblock(self.album_change)

	def on_album_view_button_press_event(self, widget, event):
		path = widget.get_path_at_pos(int(event.x), int(event.y))
		if not path == None:
			if not event.button == 1:
				treeiter=self.store.get_iter(path)
				selected_album=self.store.get_value(treeiter, 3)
				selected_album_year=self.store.get_value(treeiter, 4)
				selected_artist=self.store.get_value(treeiter, 5)
			if event.button == 2:
				self.client.album_to_playlist(selected_album, selected_artist, selected_album_year, True)
			elif event.button == 3:
				if self.client.connected():
					album = AlbumDialog(self.window, self.client, self.settings, selected_album, selected_artist, selected_album_year)
					response = album.run()
					if response == Gtk.ResponseType.OK:
						self.select_path(path)
					elif response == Gtk.ResponseType.ACCEPT:
						self.client.album_to_playlist(selected_album, selected_artist, selected_album_year, True)
					elif response == Gtk.ResponseType.YES:
						self.client.album_to_playlist(selected_album, selected_artist, selected_album_year, False, True)
					album.destroy()

	def on_album_selection_change(self, widget):
		paths=widget.get_selected_items()
		if not len(paths) == 0:
			treeiter=self.store.get_iter(paths[0])
			selected_album=self.store.get_value(treeiter, 3)
			selected_album_year=self.store.get_value(treeiter, 4)
			selected_artist=self.store.get_value(treeiter, 5)
			self.client.album_to_playlist(selected_album, selected_artist, selected_album_year, False)

	def on_album_item_activated(self, widget, path):
		treeiter=self.store.get_iter(path)
		selected_album=self.store.get_value(treeiter, 3)
		selected_album_year=self.store.get_value(treeiter, 4)
		selected_artist=self.store.get_value(treeiter, 5)
		self.client.album_to_playlist(selected_album, selected_artist, selected_album_year, False, True)

	def on_move_event(self, widget, event):
		self.grab_focus()

class AlbumView(Gtk.ScrolledWindow):
	def __init__(self, client, settings, genre_select, window):
		Gtk.ScrolledWindow.__init__(self)
		self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

		#adding vars
		self.settings=settings
		self.client=client
		self.genre_select=genre_select
		self.window=window
		self.artists=[]

		self.iconview=AlbumIconView(self.client, self.settings, self.genre_select, self.window)
		self.iconview.connect("stopped", self.update)

		self.add(self.iconview)

	def update(self, *args):
		if self.client.connected():
			self.iconview.populate(self.artists)

	def clear(self):
		self.artists=[]
		if self.iconview.stop_flag:
			self.iconview.store.clear()
		else:
			self.iconview.stop_flag=True

	def refresh(self, artists):
		if artists != self.artists:
			self.artists=artists
			if self.iconview.stop_flag:
				self.iconview.store.clear()
				self.iconview.emit("stopped")
			else:
				self.iconview.stop_flag=True

	def scroll_to_selected_album(self):
		self.iconview.scroll_to_selected_album()

class MainCover(Gtk.EventBox):
	def __init__(self, client, settings, emitter, window):
		Gtk.EventBox.__init__(self)

		#adding vars
		self.client=client
		self.settings=settings
		self.emitter=emitter
		self.window=window
		self.song_file=None

		#cover
		self.cover=Gtk.Image.new()
		self.cover.set_from_pixbuf(Cover(client=self.client, lib_path=self.settings.get_value("paths")[self.settings.get_int("active-profile")], song_file=None).get_pixbuf(self.settings.get_int("track-cover"))) #set to fallback cover

		#connect
		self.connect("button-press-event", self.on_button_press_event)
		self.player_changed=self.emitter.connect("player", self.refresh)

		self.add(self.cover)

	def refresh(self, *args):
		try:
			song_file=self.client.currentsong()["file"]
		except:
			song_file=None
		if not song_file == self.song_file:
			self.cover.set_from_pixbuf(Cover(client=self.client, lib_path=self.settings.get_value("paths")[self.settings.get_int("active-profile")], song_file=song_file).get_pixbuf(self.settings.get_int("track-cover")))
			self.song_file=song_file

	def on_button_press_event(self, widget, event):
		if self.client.connected():
			song=self.client.currentsong()
			if not song == {}:
				try:
					artist=song[self.settings.get_artist_type()]
				except:
					artist=""
				try:
					album=song["album"]
				except:
					album=""
				try:
					album_year=song["date"]
				except:
					album_year=""
				if event.button == 1:
					self.client.album_to_playlist(album, artist, album_year, False)
				elif event.button == 2:
					self.client.album_to_playlist(album, artist, album_year, True)
				elif event.button == 3:
					album_dialog = AlbumDialog(self.window, self.client, self.settings, album, artist, album_year)
					response = album_dialog.run()
					if response == Gtk.ResponseType.OK:
						self.client.album_to_playlist(album, artist, album_year, False)
					elif response == Gtk.ResponseType.ACCEPT:
						self.client.album_to_playlist(album, artist, album_year, True)
					elif response == Gtk.ResponseType.YES:
						self.client.album_to_playlist(album, artist, album_year, False, True)
					album_dialog.destroy()

	def clear(self, *args):
		self.cover.set_from_pixbuf(Cover(client=self.client, lib_path=self.settings.get_value("paths")[self.settings.get_int("active-profile")], song_file=None).get_pixbuf(self.settings.get_int("track-cover")))
		self.song_file=None

class TrackView(Gtk.Box):
	def __init__(self, client, settings, emitter):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

		#adding vars
		self.client=client
		self.settings=settings #currently unused
		self.emitter=emitter
		self.hovered_songpos=None
		self.playlist_version=None
		self.last_song_iter=None

		#Store
		#(track, title, artist, album, duration, file, weight)
		self.store = Gtk.ListStore(str, str, str, str, str, str, Pango.Weight)

		#TreeView
		self.treeview = Gtk.TreeView(model=self.store)
		self.treeview.set_search_column(-1)
		self.treeview.columns_autosize()
		self.treeview.set_property("activate-on-single-click", True)

		#selection
		self.selection = self.treeview.get_selection()
		self.selection.set_mode(Gtk.SelectionMode.SINGLE)

		#Column
		renderer_text = Gtk.CellRendererText()

		self.column_track = Gtk.TreeViewColumn(_("No"), renderer_text, text=0, weight=6)
		self.column_track.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_track.set_property("resizable", False)
		self.treeview.append_column(self.column_track)

		self.column_title = Gtk.TreeViewColumn(_("Title"), renderer_text, text=1, weight=6)
		self.column_title.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_title.set_property("resizable", True)
		self.treeview.append_column(self.column_title)

		self.column_artist = Gtk.TreeViewColumn(_("Artist"), renderer_text, text=2, weight=6)
		self.column_artist.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_artist.set_property("resizable", True)
		self.treeview.append_column(self.column_artist)

		self.column_duration = Gtk.TreeViewColumn(_("Length"), renderer_text, text=4, weight=6)
		self.column_duration.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_duration.set_property("resizable", False)
		self.treeview.append_column(self.column_duration)

		#scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(self.treeview)

		#audio infos
		audio=AudioType(self.client)

		#playlist info
		self.playlist_info=Gtk.Label()
		self.playlist_info.set_xalign(0)
		self.playlist_info.set_ellipsize(Pango.EllipsizeMode.END)

		#status bar
		status_bar=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
		status_bar.set_margin_start(4)
		status_bar.set_margin_end(4)
		status_bar.pack_start(self.playlist_info, True, True, 0)
		status_bar.pack_end(audio, False, False, 0)

		#connect
		self.treeview.connect("row-activated", self.on_row_activated)
		self.treeview.connect("motion-notify-event", self.on_move_event)
		self.treeview.connect("leave-notify-event", self.on_focus_out_event)
		self.treeview.connect("focus-out-event", self.on_focus_out_event)
		self.key_press_event=self.treeview.connect("key-press-event", self.on_key_press_event)

		self.playlist_changed=self.emitter.connect("playlist", self.on_playlist_changed)
		self.player_changed=self.emitter.connect("player", self.on_player_changed)
		self.disconnected_signal=self.emitter.connect("disconnected", self.on_disconnected)

		#packing
		self.pack_start(scroll, True, True, 0)
		self.pack_end(status_bar, False, False, 0)

	def scroll_to_selected_title(self):
		treeview, treeiter=self.selection.get_selected()
		if not treeiter == None:
			path=treeview.get_path(treeiter)
			self.treeview.scroll_to_cell(path)

	def refresh_playlist_info(self):
		songs=self.client.playlistinfo()
		if not songs == []:
			whole_length=float(0)
			for song in songs:
				try:
					dura=float(song["duration"])
				except:
					dura=0.0
				whole_length=whole_length+dura
			whole_length_human_readable=str(datetime.timedelta(seconds=int(whole_length)))
			self.playlist_info.set_text(_("%(total_tracks)i titles (%(total_length)s)") % {"total_tracks": len(songs), "total_length": whole_length_human_readable})
		else:
			self.playlist_info.set_text("")

	def refresh_selection(self): #Gtk.TreePath(len(self.store) is used to generate an invalid TreePath (needed to unset cursor)
		self.treeview.set_cursor(Gtk.TreePath(len(self.store)), None, False)
		try:
			song=self.client.status()["song"]
			path = Gtk.TreePath(int(song))
			self.selection.select_path(path)
			if self.last_song_iter != None and self.store.iter_is_valid(self.last_song_iter):
				self.store.set_value(self.last_song_iter, 6, Pango.Weight.BOOK)
			treeiter=self.store.get_iter(path)
			self.store.set_value(treeiter, 6, Pango.Weight.BOLD)
			self.last_song_iter=treeiter
		except:
			if self.last_song_iter != None:
				self.store.set_value(self.last_song_iter, 6, Pango.Weight.BOOK)
			self.last_song_iter=None
			self.selection.unselect_all()

	def clear(self, *args):
		self.playlist_info.set_text("")
		self.store.clear()
		self.playlist_version=None

	def on_key_press_event(self, widget, event):
		self.treeview.handler_block(self.key_press_event)
		if event.keyval == 65535: #entf
			if not self.hovered_songpos == None:
				try:
					self.client.delete(self.hovered_songpos) #bad song index possible
					self.store.remove(self.store.get_iter(self.hovered_songpos))
					self.playlist_version=self.client.status()["playlist"]
				except:
					self.hovered_songpos == None
		self.treeview.handler_unblock(self.key_press_event)

	def on_move_event(self, widget, event):
		treeiter=self.selection.get_selected()[1]
		if not treeiter == None:
			self.treeview.grab_focus()
			return_tuple = self.treeview.get_path_at_pos(int(event.x), int(event.y))
			if not return_tuple == None:
				self.hovered_songpos=return_tuple[0]
			else:
				self.hovered_songpos=None

	def on_focus_out_event(self, widget, event):
		self.refresh_selection()
		self.hovered_songpos=None

	def on_row_activated(self, widget, path, view_column): #TODO
		treeiter=self.store.get_iter(path)
		selected_title=self.store.get_path(treeiter)
		self.client.play(selected_title)

	def on_playlist_changed(self, *args):
		songs=[]
		if not self.playlist_version == None:
			songs=self.client.plchanges(self.playlist_version)
		else:
			songs=self.client.playlistinfo()
		if not songs == []:
			self.playlist_info.set_text("")
			for song in songs:
				try:
					title=song["title"]
				except:
					title=_("Unknown Title")
				try:
					track=song["track"].zfill(2)
				except:
					track="00"
				try:
					artist=song["artist"]
				except:
					artist=_("Unknown Artist")
				try:
					album=song["album"]
				except:
					album=_("Unknown Album")
				try:
					dura=float(song["duration"])
				except:
					dura=0.0
				duration=str(datetime.timedelta(seconds=int(dura )))
				try:
					treeiter=self.store.get_iter(song["pos"])
					self.store.set(treeiter, 0, track, 1, title, 2, artist, 3, album, 4, duration, 5, song["file"], 6, Pango.Weight.BOOK)
				except:
					self.store.append([track, title, artist, album, duration, song["file"], Pango.Weight.BOOK])
		for i in reversed(range(int(self.client.status()["playlistlength"]), len(self.store))):
			treeiter=self.store.get_iter(i)
			self.store.remove(treeiter)
		self.refresh_playlist_info()
		self.refresh_selection()
		self.playlist_version=self.client.status()["playlist"]

	def on_player_changed(self, *args):
		if not self.client.song_to_delete == "": #TODO should be in Client class
			status=self.client.status()
			if not status["song"] == "0" and self.client.playlistinfo()[0]["file"] == self.client.song_to_delete:
				self.client.delete(0)
				self.client.song_to_delete=""
			else:
				self.refresh_selection()
				self.client.song_to_delete=""
		else:
			self.refresh_selection()

	def on_disconnected(self, *args):
		self.playlist_version=None

class Browser(Gtk.Box):
	def __init__(self, client, settings, emitter, window):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=4)

		#adding vars
		self.client=client
		self.emitter=emitter
		self.settings=settings
		self.window=window

		#widgets
		self.genre_select=GenreSelect(self.client, self.settings, self.emitter)
		self.genre_select.set_margin_start(2)
		self.genre_select.set_margin_end(2)
		self.genre_select.set_margin_top(2)
		self.artist_list=ArtistView(self.client, self.settings, self.emitter, self.genre_select)
		self.album_list=AlbumView(self.client, self.settings, self.genre_select, self.window)
		self.main_cover=MainCover(self.client, self.settings, self.emitter, self.window)
		self.title_list=TrackView(self.client, self.settings, self.emitter)

		#connect
		self.artist_change=self.artist_list.selection.connect("changed", self.on_artist_selection_change)
		self.settings.connect("changed::show-genre-filter", self.on_settings_changed)

		#packing
		self.vbox1=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
		if self.settings.get_boolean("show-genre-filter"):
			self.vbox1.pack_start(self.genre_select, False, False, 0)
		self.vbox1.pack_start(self.artist_list, True, True, 0)
		self.vbox2=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
		self.vbox2.pack_start(self.main_cover, False, False, 0)
		self.vbox2.pack_start(self.title_list, True, True, 0)
		self.paned1=Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
		self.paned1.set_wide_handle(True)
		self.paned2=Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
		self.paned2.set_wide_handle(True)
		self.paned1.pack1(self.vbox1, False, False)
		self.paned1.pack2(self.album_list, True, False)
		self.paned2.pack1(self.paned1, True, False)
		self.paned2.pack2(self.vbox2, False, False)
		self.load_settings()
		self.pack_start(self.paned2, True, True, 0)

	def save_settings(self):
		self.settings.set_int("paned1", self.paned1.get_position())
		self.settings.set_int("paned2", self.paned2.get_position())

	def load_settings(self):
		self.paned1.set_position(self.settings.get_int("paned1"))
		self.paned2.set_position(self.settings.get_int("paned2"))

	def clear(self, *args):
		self.artist_list.selection.handler_block(self.artist_change)
		self.artist_list.clear()
		self.artist_list.selection.handler_unblock(self.artist_change)
		self.album_list.clear()
		self.title_list.clear()
		self.main_cover.clear()

	def go_home(self, *args): #TODO
		try:
			songid=self.client.status()["songid"]
			song=self.client.playlistid(songid)[0]
			row_num=len(self.artist_list.store)
			for i in range(0, row_num):
				path=Gtk.TreePath(i)
				treeiter = self.artist_list.store.get_iter(path)
				if self.artist_list.store.get_value(treeiter, 0) == song[self.settings.get_artist_type()]:
					if not self.artist_list.selection.iter_is_selected(treeiter):
						self.artist_list.selection.handler_block(self.artist_change)
						self.artist_list.selection.unselect_all()
						self.artist_list.selection.handler_unblock(self.artist_change)
						self.artist_list.treeview.set_cursor(path, None, False)
					break
			self.album_list.scroll_to_selected_album()
		except:
			pass
		self.title_list.scroll_to_selected_title()

	def on_artist_selection_change(self, *args):
		artists=self.artist_list.get_selected_artists()
		self.album_list.refresh(artists)

	def on_settings_changed(self, *args):
		if self.settings.get_boolean("show-genre-filter"):
			self.vbox1.pack_start(self.genre_select, False, False, 0)
			self.vbox1.reorder_child(self.genre_select, 0)
			self.genre_select.show_all()
		else:
			self.genre_select.deactivate()
			self.vbox1.remove(self.genre_select)

class ProfileSettings(Gtk.Grid):
	def __init__(self, parent, settings):
		Gtk.Grid.__init__(self)
		self.set_row_spacing(4)
		self.set_column_spacing(4)
		self.set_property("border-width", 4)

		#adding vars
		self.settings = settings

		#widgets
		self.profiles_combo=Gtk.ComboBoxText()
		self.profiles_combo.set_entry_text_column(0)

		add_button=Gtk.Button(label=None, image=Gtk.Image(stock=Gtk.STOCK_ADD))
		delete_button=Gtk.Button(label=None, image=Gtk.Image(stock=Gtk.STOCK_DELETE))

		self.profile_entry=Gtk.Entry()
		self.host_entry=Gtk.Entry()
		self.port_entry=IntEntry(0, 0, 65535)
		self.password_entry=Gtk.Entry()
		self.password_entry.set_visibility(False)
		self.path_select_button=Gtk.Button(label=_("Select"), image=Gtk.Image(stock=Gtk.STOCK_OPEN))

		profiles_label=Gtk.Label(label=_("Profile:"))
		profiles_label.set_xalign(1)
		profile_label=Gtk.Label(label=_("Name:"))
		profile_label.set_xalign(1)
		host_label=Gtk.Label(label=_("Host:"))
		host_label.set_xalign(1)
		port_label=Gtk.Label(label=_("Port:"))
		port_label.set_xalign(1)
		password_label=Gtk.Label(label=_("Password:"))
		password_label.set_xalign(1)
		path_label=Gtk.Label(label=_("Music lib:"))
		path_label.set_xalign(1)

		#connect
		self.profile_entry_changed=self.profile_entry.connect("changed", self.on_profile_entry_changed)
		self.host_entry_changed=self.host_entry.connect("changed", self.on_host_entry_changed)
		self.port_entry_changed=self.port_entry.connect("value-changed", self.on_port_entry_changed)
		self.password_entry_changed=self.password_entry.connect("changed", self.on_password_entry_changed)
		self.path_select_button.connect("clicked", self.on_path_select_button_clicked, parent)
		add_button.connect("clicked", self.on_add_button_clicked)
		delete_button.connect("clicked", self.on_delete_button_clicked)
		self.profiles_combo_changed=self.profiles_combo.connect("changed", self.on_profiles_changed)

		self.profiles_combo_reload()
		self.profiles_combo.set_active(0)

		#packing
		self.add(profiles_label)
		self.attach_next_to(profile_label, profiles_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(host_label, profile_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(port_label, host_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(password_label, port_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(path_label, password_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(self.profiles_combo, profiles_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(add_button, self.profiles_combo, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(delete_button, add_button, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(self.profile_entry, profile_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(self.host_entry, host_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(self.port_entry, port_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(self.password_entry, password_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(self.path_select_button, path_label, Gtk.PositionType.RIGHT, 1, 1)

	def profiles_combo_reload(self, *args):
		self.profiles_combo.handler_block(self.profiles_combo_changed)
		self.profile_entry.handler_block(self.profile_entry_changed)
		self.host_entry.handler_block(self.host_entry_changed)
		self.port_entry.handler_block(self.port_entry_changed)

		self.profiles_combo.remove_all()
		for profile in self.settings.get_value("profiles"):
			self.profiles_combo.append_text(profile)

		self.profiles_combo.handler_unblock(self.profiles_combo_changed)
		self.profile_entry.handler_unblock(self.profile_entry_changed)
		self.host_entry.handler_unblock(self.host_entry_changed)
		self.port_entry.handler_unblock(self.port_entry_changed)

	def on_add_button_clicked(self, *args):
		pos=self.profiles_combo.get_active()
		self.settings.array_append('as', "profiles", "new profile")
		self.settings.array_append('as', "hosts", "localhost")
		self.settings.array_append('ai', "ports", 6600)
		self.settings.array_append('as', "passwords", "")
		self.settings.array_append('as', "paths", "")
		self.profiles_combo_reload()
		self.profiles_combo.set_active(pos)

	def on_delete_button_clicked(self, *args):
		pos=self.profiles_combo.get_active()
		self.settings.array_delete('as', "profiles", pos)
		self.settings.array_delete('as', "hosts", pos)
		self.settings.array_delete('ai', "ports", pos)
		self.settings.array_delete('as', "passwords", pos)
		self.settings.array_delete('as', "paths", pos)
		if len(self.settings.get_value("profiles")) == 0:
			self.on_add_button_clicked()
		else:
			self.profiles_combo_reload()
			self.profiles_combo.set_active(0)	

	def on_profile_entry_changed(self, *args):
		pos=self.profiles_combo.get_active()
		self.settings.array_modify('as', "profiles", pos, self.profile_entry.get_text())
		self.profiles_combo_reload()
		self.profiles_combo.set_active(pos)

	def on_host_entry_changed(self, *args):
		self.settings.array_modify('as', "hosts", self.profiles_combo.get_active(), self.host_entry.get_text())

	def on_port_entry_changed(self, *args):
		self.settings.array_modify('ai', "ports", self.profiles_combo.get_active(), self.port_entry.get_int())

	def on_password_entry_changed(self, *args):
		self.settings.array_modify('as', "passwords", self.profiles_combo.get_active(), self.password_entry.get_text())

	def on_path_select_button_clicked(self, widget, parent):
		dialog = Gtk.FileChooserDialog(title=_("Choose directory"), transient_for=parent, action=Gtk.FileChooserAction.SELECT_FOLDER)
		dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)
		dialog.set_default_size(800, 400)
		dialog.set_current_folder(self.settings.get_value("paths")[self.profiles_combo.get_active()])
		response = dialog.run()
		if response == Gtk.ResponseType.OK:
			self.settings.array_modify('as', "paths", self.profiles_combo.get_active(), dialog.get_filename())
			self.path_select_button.set_tooltip_text(dialog.get_filename())
		dialog.destroy()

	def on_profiles_changed(self, *args):
		active=self.profiles_combo.get_active()
		self.profile_entry.handler_block(self.profile_entry_changed)
		self.host_entry.handler_block(self.host_entry_changed)
		self.port_entry.handler_block(self.port_entry_changed)
		self.password_entry.handler_block(self.password_entry_changed)

		self.profile_entry.set_text(self.settings.get_value("profiles")[active])
		self.host_entry.set_text(self.settings.get_value("hosts")[active])
		self.port_entry.set_int(self.settings.get_value("ports")[active])
		self.password_entry.set_text(self.settings.get_value("passwords")[active])
		self.path_select_button.set_tooltip_text(self.settings.get_value("paths")[active])

		self.profile_entry.handler_unblock(self.profile_entry_changed)
		self.host_entry.handler_unblock(self.host_entry_changed)
		self.port_entry.handler_unblock(self.port_entry_changed)
		self.password_entry.handler_unblock(self.password_entry_changed)

class GeneralSettings(Gtk.Grid):
	def __init__(self, settings):
		Gtk.Grid.__init__(self)
		self.set_row_spacing(4)
		self.set_column_spacing(4)
		self.set_property("border-width", 4)

		#adding vars
		self.settings = settings

		#widgets
		track_cover_label=Gtk.Label(label=_("Main cover size:"))
		track_cover_label.set_xalign(1)
		album_cover_label=Gtk.Label(label=_("Album-view cover size:"))
		album_cover_label.set_xalign(1)

		track_cover_size=IntEntry(self.settings.get_int("track-cover"), 100, 1200)
		album_cover_size=IntEntry(self.settings.get_int("album-cover"), 50, 600)

		icon_size_label=Gtk.Label(label=_("Button icon size (restart required):"))
		icon_size_label.set_xalign(1)
		icon_size_combo=Gtk.ComboBoxText()
		icon_size_combo.set_entry_text_column(0)
		sizes=[16, 24, 32, 48]
		for i in sizes:
			icon_size_combo.append_text(str(i))
		icon_size_combo.set_active(sizes.index(self.settings.get_int("icon-size")))

		show_stop=Gtk.CheckButton(label=_("Show stop button"))
		show_stop.set_active(self.settings.get_boolean("show-stop"))

		show_genre_filter=Gtk.CheckButton(label=_("Show genre filter"))
		show_genre_filter.set_active(self.settings.get_boolean("show-genre-filter"))

		show_album_view_tooltips=Gtk.CheckButton(label=_("Show tooltips in album view"))
		show_album_view_tooltips.set_active(self.settings.get_boolean("show-album-view-tooltips"))

		sort_albums_by_year=Gtk.CheckButton(label=_("Sort albums by year"))
		sort_albums_by_year.set_active(self.settings.get_boolean("sort-albums-by-year"))

		show_all_artists=Gtk.CheckButton(label=_("Show all artists"))
		show_all_artists.set_active(self.settings.get_boolean("show-all-artists"))

		send_notify=Gtk.CheckButton(label=_("Send notification on title change"))
		send_notify.set_active(self.settings.get_boolean("send-notify"))

		stop_on_quit=Gtk.CheckButton(label=_("Stop playback on quit"))
		stop_on_quit.set_active(self.settings.get_boolean("stop-on-quit"))

		add_album=Gtk.CheckButton(label=_("Play selected album after current title"))
		add_album.set_active(self.settings.get_boolean("add-album"))

		#connect
		track_cover_size.connect("value-changed", self.on_int_changed, "track-cover")
		album_cover_size.connect("value-changed", self.on_int_changed, "album-cover")
		icon_size_combo.connect("changed", self.on_icon_size_changed)
		show_stop.connect("toggled", self.on_toggled, "show-stop")
		show_genre_filter.connect("toggled", self.on_toggled, "show-genre-filter")
		show_album_view_tooltips.connect("toggled", self.on_toggled, "show-album-view-tooltips")
		sort_albums_by_year.connect("toggled", self.on_toggled, "sort-albums-by-year")
		show_all_artists.connect("toggled", self.on_toggled, "show-all-artists")
		send_notify.connect("toggled", self.on_toggled, "send-notify")
		stop_on_quit.connect("toggled", self.on_toggled, "stop-on-quit")
		add_album.connect("toggled", self.on_toggled, "add-album")

		#packing
		self.add(track_cover_label)
		self.attach_next_to(album_cover_label, track_cover_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(icon_size_label, album_cover_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(track_cover_size, track_cover_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(album_cover_size, album_cover_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(icon_size_combo, icon_size_label, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(show_stop, icon_size_label, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(show_genre_filter, show_stop, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(show_album_view_tooltips, show_genre_filter, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(sort_albums_by_year, show_album_view_tooltips, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(show_all_artists, sort_albums_by_year, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(send_notify, show_all_artists, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(add_album, send_notify, Gtk.PositionType.BOTTOM, 2, 1)
		self.attach_next_to(stop_on_quit, add_album, Gtk.PositionType.BOTTOM, 2, 1)

	def on_int_changed(self, widget, key):
		self.settings.set_int(key, widget.get_int())

	def on_toggled(self, widget, key):
		self.settings.set_boolean(key, widget.get_active())

	def on_icon_size_changed(self, box):
		active_size=int(box.get_active_text())
		self.settings.set_int("icon-size", active_size)

class SettingsDialog(Gtk.Dialog):
	def __init__(self, parent, settings):
		Gtk.Dialog.__init__(self, title=_("Settings"), transient_for=parent)
		self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
		self.set_default_size(500, 400)

		#adding vars
		self.settings = settings

		#widgets
		general=GeneralSettings(self.settings)
		profiles=ProfileSettings(parent, self.settings)

		#packing
		tabs = Gtk.Notebook()
		tabs.append_page(general, Gtk.Label(label=_("General")))
		tabs.append_page(profiles, Gtk.Label(label=_("Profiles")))
		self.vbox.pack_start(tabs, True, True, 0) #vbox default widget of dialogs
		self.vbox.set_spacing(6)

		self.show_all()

class ClientControl(Gtk.ButtonBox):
	def __init__(self, client, settings, emitter):
		Gtk.ButtonBox.__init__(self, spacing=4)

		#adding vars
		self.client=client
		self.settings=settings
		self.emitter=emitter
		self.icon_size=self.settings.get_gtk_icon_size("icon-size")

		#widgets
		self.play_button = Gtk.Button(image=Gtk.Image.new_from_icon_name("media-playback-start-symbolic", self.icon_size))
		self.stop_button = Gtk.Button(image=Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", self.icon_size))
		self.stop_button.set_can_focus(False)
		self.prev_button = Gtk.Button(image=Gtk.Image.new_from_icon_name("media-skip-backward-symbolic", self.icon_size))
		self.prev_button.set_can_focus(False)
		self.next_button = Gtk.Button(image=Gtk.Image.new_from_icon_name("media-skip-forward-symbolic", self.icon_size))
		self.next_button.set_can_focus(False)

		#connect
		self.play_button.connect("clicked", self.on_play_clicked)
		self.stop_button.connect("clicked", self.on_stop_clicked)
		self.prev_button.connect("clicked", self.on_prev_clicked)
		self.next_button.connect("clicked", self.on_next_clicked)
		self.settings.connect("changed::show-stop", self.on_settings_changed)
		self.player_changed=self.emitter.connect("player", self.update)

		#packing
		self.pack_start(self.prev_button, True, True, 0)
		self.pack_start(self.play_button, True, True, 0)
		if self.settings.get_boolean("show-stop"):
			self.pack_start(self.stop_button, True, True, 0)
		self.pack_start(self.next_button, True, True, 0)

	def update(self, *args):
		status=self.client.status()
		if status["state"] == "play":
			self.play_button.set_image(Gtk.Image.new_from_icon_name("media-playback-pause-symbolic", self.icon_size))
			self.prev_button.set_sensitive(True)
			self.next_button.set_sensitive(True)
		elif status["state"] == "pause":
			self.play_button.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", self.icon_size))
			self.prev_button.set_sensitive(True)
			self.next_button.set_sensitive(True)
		else:
			self.play_button.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", self.icon_size))
			self.prev_button.set_sensitive(False)
			self.next_button.set_sensitive(False)

	def on_play_clicked(self, widget):
		if self.client.connected():
			status=self.client.status()
			if status["state"] == "play":
				self.client.pause(1)
			elif status["state"] == "pause":
				self.client.pause(0)
			else:
				try:
					self.client.play(status["song"])
				except:
					try:
						self.client.play()
					except:
						pass
			self.update()

	def on_stop_clicked(self, widget):
		if self.client.connected():
			self.client.stop()
			self.update()

	def on_prev_clicked(self, widget):
		if self.client.connected():
			self.client.previous()

	def on_next_clicked(self, widget):
		if self.client.connected():
			self.client.next()

	def on_settings_changed(self, *args):
		if self.settings.get_boolean("show-stop"):
			self.pack_start(self.stop_button, True, True, 0)
			self.reorder_child(self.stop_button, 2)
			self.stop_button.show()
		else:
			self.remove(self.stop_button)

class SeekBar(Gtk.Box):
	def __init__(self, client):
		Gtk.Box.__init__(self)

		#adding vars
		self.client=client
		self.seek_time="10" #seek increment in seconds

		#labels
		self.elapsed=Gtk.Label()
		self.elapsed.set_width_chars(7)
		self.rest=Gtk.Label()
		self.rest.set_width_chars(8)

		#progress bar
		self.scale=Gtk.Scale.new_with_range(orientation=Gtk.Orientation.HORIZONTAL, min=0, max=100, step=0.001)
		self.scale.set_draw_value(False)
		self.scale.set_can_focus(False)

		#event boxes
		self.elapsed_event_box=Gtk.EventBox()
		self.rest_event_box=Gtk.EventBox()
		self.elapsed_event_box.connect("button-press-event", self.on_elapsed_button_press_event)
		self.rest_event_box.connect("button-press-event", self.on_rest_button_press_event)

		#connect
		self.scale.connect("change-value", self.seek)
		self.scale.connect("scroll-event", self.dummy) #disable mouse wheel which caused some noise

		#timeouts
		GLib.timeout_add(100, self.update)

		#packing
		self.elapsed_event_box.add(self.elapsed)
		self.rest_event_box.add(self.rest)
		self.pack_start(self.elapsed_event_box, False, False, 0)
		self.pack_start(self.scale, True, True, 0)
		self.pack_end(self.rest_event_box, False, False, 0)

	def dummy(self, *args):
		return True

	def seek(self, range, scroll, value):
		status=self.client.status()
		duration=float(status["duration"])
		factor=(value/100)
		pos=(duration*factor)
		self.client.seekcur(pos)

	def seek_forward(self):
		self.client.seekcur("+"+self.seek_time)

	def seek_backward(self):
		self.client.seekcur("-"+self.seek_time)

	def on_elapsed_button_press_event(self, widget, event):
		if event.button == 1:
			self.seek_backward()
		elif event.button == 3:
			self.seek_forward()

	def on_rest_button_press_event(self, widget, event):
		if event.button == 1:
			self.seek_forward()
		elif event.button == 3:
			self.seek_backward()

	def update(self):
		try:
			status=self.client.status()
			duration=float(status["duration"])
			elapsed=float(status["elapsed"])
			fraction=(elapsed/duration)*100
			self.scale.set_value(fraction)
			self.elapsed.set_text(str(datetime.timedelta(seconds=int(elapsed))))
			self.rest.set_text("-"+str(datetime.timedelta(seconds=int(duration-elapsed))))
			self.scale.set_sensitive(True)
			self.elapsed_event_box.set_sensitive(True)
			self.rest_event_box.set_sensitive(True)
		except:
			self.scale.set_value(0.0)
			self.elapsed.set_text("0:00:00")
			self.rest.set_text("-0:00:00")
			self.scale.set_sensitive(False)
			self.elapsed_event_box.set_sensitive(False)
			self.rest_event_box.set_sensitive(False)
		return True

class PlaybackOptions(Gtk.Box):
	def __init__(self, client, settings, emitter):
		Gtk.Box.__init__(self)

		#adding vars
		self.client=client
		self.settings=settings
		self.emitter=emitter
		self.icon_size=self.settings.get_gtk_icon_size("icon-size")

		#widgets
		self.random=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("media-playlist-shuffle-symbolic", self.icon_size))
		self.random.set_can_focus(False)
		self.random.set_tooltip_text(_("Random mode"))
		self.repeat=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("media-playlist-repeat-symbolic", self.icon_size))
		self.repeat.set_can_focus(False)
		self.repeat.set_tooltip_text(_("Repeat mode"))
		self.single=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("zoom-original-symbolic", self.icon_size))
		self.single.set_can_focus(False)
		self.single.set_tooltip_text(_("Single mode"))
		self.consume=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("edit-cut-symbolic", self.icon_size))
		self.consume.set_can_focus(False)
		self.consume.set_tooltip_text(_("Consume mode"))
		self.volume=Gtk.VolumeButton()
		self.volume.set_can_focus(False)
		self.volume.set_property("size", self.icon_size)

		#connect
		self.random_toggled=self.random.connect("toggled", self.set_random)
		self.repeat_toggled=self.repeat.connect("toggled", self.set_repeat)
		self.single_toggled=self.single.connect("toggled", self.set_single)
		self.consume_toggled=self.consume.connect("toggled", self.set_consume)
		self.volume_changed=self.volume.connect("value-changed", self.set_volume)
		self.options_changed=self.emitter.connect("options", self.options_update)
		self.mixer_changed=self.emitter.connect("mixer", self.mixer_update)

		#packing
		ButtonBox=Gtk.ButtonBox()
		ButtonBox.set_property("layout-style", Gtk.ButtonBoxStyle.EXPAND)
		ButtonBox.pack_start(self.repeat, True, True, 0)
		ButtonBox.pack_start(self.random, True, True, 0)
		ButtonBox.pack_start(self.single, True, True, 0)
		ButtonBox.pack_start(self.consume, True, True, 0)
		self.pack_start(ButtonBox, True, True, 0)
		self.pack_start(self.volume, True, True, 0)

	def set_random(self, widget):
		if widget.get_active():
			self.client.random("1")
		else:
			self.client.random("0")

	def set_repeat(self, widget):
		if widget.get_active():
			self.client.repeat("1")
		else:
			self.client.repeat("0")

	def set_single(self, widget):
		if widget.get_active():
			self.client.single("1")
		else:
			self.client.single("0")

	def set_consume(self, widget):
		if widget.get_active():
			self.client.consume("1")
		else:
			self.client.consume("0")

	def set_volume(self, widget, value):
		self.client.setvol(str(int(value*100)))

	def options_update(self, *args):
		self.repeat.handler_block(self.repeat_toggled)
		self.random.handler_block(self.random_toggled)
		self.single.handler_block(self.single_toggled)
		self.consume.handler_block(self.consume_toggled)
		status=self.client.status()
		if status["repeat"] == "0":
			self.repeat.set_active(False)
		else:
			self.repeat.set_active(True)
		if status["random"] == "0":
			self.random.set_active(False)
		else:
			self.random.set_active(True)
		if status["single"] == "0":
			self.single.set_active(False)
		else:
			self.single.set_active(True)
		if status["consume"] == "0":
			self.consume.set_active(False)
		else:
			self.consume.set_active(True)
		self.repeat.handler_unblock(self.repeat_toggled)
		self.random.handler_unblock(self.random_toggled)
		self.single.handler_unblock(self.single_toggled)
		self.consume.handler_unblock(self.consume_toggled)

	def mixer_update(self, *args):
		self.volume.handler_block(self.volume_changed)
		status=self.client.status()
		try:
			self.volume.set_value((int(status["volume"])/100))
		except:
			self.volume.set_value(0)
		self.volume.handler_unblock(self.volume_changed)

class AudioType(Gtk.EventBox):
	def __init__(self, client):
		Gtk.EventBox.__init__(self)
		self.set_tooltip_text(_("Click to show additional information"))

		#adding vars
		self.client=client

		#widgets
		self.label=Gtk.Label()
		self.label.set_xalign(1)
		self.label.set_ellipsize(Pango.EllipsizeMode.END)
		self.popover=Gtk.Popover()
		self.popover.set_relative_to(self)

		#Store
		#(tag, value)
		self.store = Gtk.ListStore(str, str)

		#TreeView
		self.treeview = Gtk.TreeView(model=self.store)
		self.treeview.set_search_column(-1)
		sel = self.treeview.get_selection()
		sel.set_mode(Gtk.SelectionMode.NONE)

		#Column
		renderer_text = Gtk.CellRendererText()

		self.column_tag = Gtk.TreeViewColumn(_("MPD-Tag"), renderer_text, text=0)
		self.column_tag.set_property("resizable", False)
		self.treeview.append_column(self.column_tag)

		self.column_value = Gtk.TreeViewColumn(_("Value"), renderer_text, text=1)
		self.column_value.set_property("resizable", False)
		self.treeview.append_column(self.column_value)

		#timeouts
		GLib.timeout_add(1000, self.update)

		#connect
		self.connect("button-press-event", self.on_button_press_event)

		#packing
		self.popover.add(self.treeview)
		self.add(self.label)

	def update(self):
		if self.client.connected():
			status=self.client.status()
			try:
				file_type=self.client.playlistinfo(status["song"])[0]["file"].split('.')[-1]
				freq, res, chan = status["audio"].split(':')
				freq=str(float(freq)/1000)
				brate = status["bitrate"]
				string=_("%(bitrate)s kb/s, %(frequency)s kHz, %(resolution)s bit, %(channels)s channels, %(file_type)s") % {"bitrate": brate, "frequency": freq, "resolution": res, "channels": chan, "file_type": file_type}
				self.label.set_text(string)
			except:
				self.label.set_text("-")
		else:
			self.label.set_text("-")
		return True

	def on_button_press_event(self, widget, event):
		if event.button == 1 or event.button == 2 or event.button == 3:
			try:
				self.store.clear()
				song=self.client.status()["song"]
				tags=self.client.playlistinfo(song)[0]
				for key in tags:
					if key == "time":
						self.store.append([key, str(datetime.timedelta(seconds=int(tags[key])))])
					else:
						self.store.append([key, tags[key]])
				self.popover.show_all()
				self.treeview.queue_resize()
			except:
				pass

class ProfileSelect(Gtk.ComboBoxText):
	def __init__(self, client, settings, emitter):
		Gtk.ComboBoxText.__init__(self)

		#adding vars
		self.client=client
		self.settings=settings
		self.emitter=emitter

		#connect
		self.changed=self.connect("changed", self.on_changed)
		self.settings.connect("changed::profiles", self.on_settings_changed)
		self.settings.connect("changed::hosts", self.on_settings_changed)
		self.settings.connect("changed::ports", self.on_settings_changed)
		self.settings.connect("changed::passwords", self.on_settings_changed)
		self.settings.connect("changed::paths", self.on_settings_changed)

		self.reload()

	def reload(self, *args):
		self.handler_block(self.changed)
		self.remove_all()
		for profile in self.settings.get_value("profiles"):
			self.append_text(profile)
		self.set_active(self.settings.get_int("active-profile"))
		self.handler_unblock(self.changed)

	def on_settings_changed(self, *args):
		self.reload()

	def on_changed(self, *args):
		active=self.get_active()
		self.settings.set_int("active-profile", active)

class ServerStats(Gtk.Dialog):
	def __init__(self, parent, client):
		Gtk.Dialog.__init__(self, title=_("Stats"), transient_for=parent)

		#adding vars
		self.client=client

		#Store
		#(tag, value)
		self.store = Gtk.ListStore(str, str)

		#TreeView
		self.treeview = Gtk.TreeView(model=self.store)
		self.treeview.set_search_column(-1)
		sel = self.treeview.get_selection()
		sel.set_mode(Gtk.SelectionMode.NONE)

		#Column
		renderer_text = Gtk.CellRendererText()

		self.column_tag = Gtk.TreeViewColumn(_("Tag"), renderer_text, text=0)
		self.treeview.append_column(self.column_tag)

		self.column_value = Gtk.TreeViewColumn(_("Value"), renderer_text, text=1)
		self.treeview.append_column(self.column_value)

		stats=self.client.stats()
		for key in stats:
			if key == "uptime" or key == "playtime" or key == "db_playtime":
				self.store.append([key, str(datetime.timedelta(seconds=int(stats[key])))])
			elif key == "db_update":
				self.store.append([key, str(datetime.datetime.fromtimestamp(int(stats[key])))])
			else:
				self.store.append([key, stats[key]])

		self.vbox.pack_start(self.treeview, True, True, 0)
		self.show_all()

class SearchWindow(Gtk.Window):
	def __init__(self, client):
		Gtk.Window.__init__(self, title=_("Search"))
		self.set_icon_name("mpdevil")
		self.set_default_size(800, 600)

		#adding vars
		self.client=client

		#scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

		#search entry
		self.search_entry=Gtk.SearchEntry()
		self.search_entry.set_margin_start(2)
		self.search_entry.set_margin_end(2)
		self.search_entry.set_margin_top(2)

		#label
		self.label=Gtk.Label()
		self.label.set_xalign(1)
		self.label.set_margin_end(4)
		self.label.set_margin_bottom(2)

		#Store
		#(track, title, artist, album, duration, file)
		self.store = Gtk.ListStore(str, str, str, str, str, str)

		#TreeView
		self.treeview = Gtk.TreeView(model=self.store)
		self.treeview.set_search_column(-1)
		self.treeview.columns_autosize()

		self.selection = self.treeview.get_selection()
		self.selection.set_mode(Gtk.SelectionMode.SINGLE)

		#Column
		renderer_text = Gtk.CellRendererText()

		self.column_track = Gtk.TreeViewColumn(_("No"), renderer_text, text=0)
		self.column_track.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_track.set_property("resizable", False)
		self.column_track.set_sort_column_id(0)
		self.treeview.append_column(self.column_track)

		self.column_title = Gtk.TreeViewColumn(_("Title"), renderer_text, text=1)
		self.column_title.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_title.set_property("resizable", False)
		self.column_title.set_sort_column_id(1)
		self.treeview.append_column(self.column_title)

		self.column_artist = Gtk.TreeViewColumn(_("Artist"), renderer_text, text=2)
		self.column_artist.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_artist.set_property("resizable", False)
		self.column_artist.set_sort_column_id(2)
		self.treeview.append_column(self.column_artist)

		self.column_album = Gtk.TreeViewColumn(_("Album"), renderer_text, text=3)
		self.column_album.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_album.set_property("resizable", False)
		self.column_album.set_sort_column_id(3)
		self.treeview.append_column(self.column_album)

		self.column_time = Gtk.TreeViewColumn(_("Length"), renderer_text, text=4)
		self.column_time.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self.column_time.set_property("resizable", False)
		self.column_time.set_sort_column_id(4)
		self.treeview.append_column(self.column_time)

		#connect
		self.title_activated=self.treeview.connect("row-activated", self.on_row_activated)
		self.title_change=self.selection.connect("changed", self.on_selection_change)
		self.search_entry.connect("search-changed", self.on_search_changed)

		#packing
		scroll.add(self.treeview)
		vbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
		vbox.pack_start(self.search_entry, False, False, 0)
		vbox.pack_start(scroll, True, True, 0)
		vbox.pack_start(self.label, False, False, 0)
		self.add(vbox)

		self.show_all()

	def on_row_activated(self, widget, path, view_column):
		treeiter=self.store.get_iter(path)
		selected_title=self.store.get_value(treeiter, 5)
		self.client.clear()
		self.client.add(selected_title)
		self.client.play()

	def on_selection_change(self, widget):
		treeiter=widget.get_selected()[1]
		if not treeiter == None:
			selected_title=self.store.get_value(treeiter, 5)
			self.client.add(selected_title)

	def on_search_changed(self, widget):
		self.store.clear()
		for song in self.client.search("any", self.search_entry.get_text()):
			try:
				title=song["title"]
			except:
				title=_("Unknown Title")
			try:
				track=song["track"].zfill(2)
			except:
				track="00"
			try:
				artist=song["artist"]
			except:
				artist=_("Unknown Artist")
			try:
				album=song["album"]
			except:
				album=_("Unknown Album")
			try:
				dura=float(song["duration"])
			except:
				dura=0.0
			duration=str(datetime.timedelta(seconds=int(dura)))
			self.store.append([track, title, artist, album, duration, song["file"].replace("&", "")] )
		self.label.set_text(_("Hits: %i") % (len(self.store)))

class LyricsWindow(Gtk.Window):
	def __init__(self, client, settings, emitter):
		Gtk.Window.__init__(self, title=_("Lyrics"))
		self.set_icon_name("mpdevil")
		self.set_default_size(450, 800)

		#adding vars
		self.settings=settings
		self.client=client
		self.emitter=emitter
		self.current_song={}

		#widgets
		self.scroll=Gtk.ScrolledWindow()
		self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		self.label=Gtk.Label()
		self.label.set_selectable(True)
		self.label.set_yalign(0)
		self.label.set_xalign(0)

		#connect
		self.player_changed=self.emitter.connect("player", self.update)
		self.connect("destroy", self.remove_handlers)

		#packing
		self.scroll.add(self.label)
		self.add(self.scroll)

		self.show_all()

		self.update()

	def remove_handlers(self, *args):
		self.emitter.disconnect(self.player_changed)

	def display_lyrics(self):
		GLib.idle_add(self.label.set_text, _("searching..."))
		try:
			text=self.getLyrics(self.current_song["artist"], self.current_song["title"])
		except:
			text=_("not found")
		GLib.idle_add(self.label.set_text, text)

	def update(self, *args):
		cs=self.client.currentsong()
		if not cs == {}:
			cs.pop("pos") #avoid unnecessary reloads caused by position change of current title
		if cs != self.current_song:
			self.current_song=cs
			update_thread=threading.Thread(target=self.display_lyrics, daemon=True)
			update_thread.start()

	def getLyrics(self, singer, song): #partially copied from PyLyrics 1.1.0
		#Replace spaces with _
		singer = singer.replace(' ', '_')
		song = song.replace(' ', '_')
		r = requests.get('http://lyrics.wikia.com/{0}:{1}'.format(singer,song))
		s = BeautifulSoup(r.text)
		#Get main lyrics holder
		lyrics = s.find("div",{'class':'lyricbox'})
		if lyrics is None:
			raise ValueError("Song or Singer does not exist or the API does not have Lyrics")
			return None
		#Remove Scripts
		[s.extract() for s in lyrics('script')]
		#Remove Comments
		comments = lyrics.findAll(text=lambda text:isinstance(text, Comment))
		[comment.extract() for comment in comments]
		#Remove span tag (Needed for instrumantal)
		if not lyrics.span == None:
			lyrics.span.extract()
		#Remove unecessary tags
		for tag in ['div','i','b','a']:
			for match in lyrics.findAll(tag):
				match.replaceWithChildren()
		#Get output as a string and remove non unicode characters and replace <br> with newlines
		output = str(lyrics).encode('utf-8', errors='replace')[22:-6:].decode("utf-8").replace('\n','').replace('<br/>','\n')
		try:
			return output
		except:
			return output.encode('utf-8')

class MainWindow(Gtk.ApplicationWindow):
	def __init__(self, app, client, settings, emitter):
		Gtk.ApplicationWindow.__init__(self, title=("mpdevil"), application=app)
		Notify.init("mpdevil")
		self.set_icon_name("mpdevil")
		self.settings = settings
		self.set_default_size(self.settings.get_int("width"), self.settings.get_int("height"))

		#adding vars
		self.app=app
		self.client=client
		self.emitter=emitter
		self.icon_size=self.settings.get_gtk_icon_size("icon-size")
		self.song_file=None

		#actions
		save_action = Gio.SimpleAction.new("save", None)
		save_action.connect("activate", self.on_save)
		self.add_action(save_action)

		settings_action = Gio.SimpleAction.new("settings", None)
		settings_action.connect("activate", self.on_settings)
		self.add_action(settings_action)

		stats_action = Gio.SimpleAction.new("stats", None)
		stats_action.connect("activate", self.on_stats)
		self.add_action(stats_action)

		update_action = Gio.SimpleAction.new("update", None)
		update_action.connect("activate", self.on_update)
		self.add_action(update_action)

		#widgets
		self.browser=Browser(self.client, self.settings, self.emitter, self)
		self.profiles=ProfileSelect(self.client, self.settings, self.emitter)
		self.profiles.set_tooltip_text(_("Select profile"))
		self.control=ClientControl(self.client, self.settings, self.emitter)
		self.progress=SeekBar(self.client)
		self.go_home_button=Gtk.Button(image=Gtk.Image.new_from_icon_name("go-home-symbolic", self.icon_size))
		self.go_home_button.set_can_focus(False)
		self.go_home_button.set_tooltip_text(_("Return to album of current title"))
		self.search_button=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("system-search-symbolic", self.icon_size))
		self.search_button.set_can_focus(False)
		self.search_button.set_tooltip_text(_("Title search"))
		self.lyrics_button=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("media-view-subtitles-symbolic", self.icon_size))
		self.lyrics_button.set_can_focus(False)
		self.lyrics_button.set_tooltip_text(_("Show lyrics"))
		self.play_opts=PlaybackOptions(self.client, self.settings, self.emitter)

		#menu
		menu = Gio.Menu()
		menu.append(_("Save window size"), "win.save")
		menu.append(_("Settings"), "win.settings")
		menu.append(_("Update database"), "win.update")
		menu.append(_("Server stats"), "win.stats")
		menu.append(_("About"), "app.about")
		menu.append(_("Quit"), "app.quit")

		menu_button = Gtk.MenuButton.new()
		menu_button.set_can_focus(False)
		menu_popover = Gtk.Popover.new_from_model(menu_button, menu)
		menu_button.set_popover(menu_popover)
		menu_button.set_tooltip_text(_("Main menu"))

		#connect
		self.go_home_button.connect("clicked", self.browser.go_home)
		self.search_button.connect("toggled", self.on_search_toggled)
		self.lyrics_button.connect("toggled", self.on_lyrics_toggled)
		self.settings.connect("changed::profiles", self.on_settings_changed)
		self.player_changed=self.emitter.connect("player", self.title_update)
		self.disconnected_signal=self.emitter.connect("disconnected", self.on_disconnected)
		self.reconnected_signal=self.emitter.connect("reconnected", self.on_reconnected)
		#unmap space
		binding_set=Gtk.binding_set_find('GtkTreeView')
		Gtk.binding_entry_remove(binding_set, 32, Gdk.ModifierType.MOD2_MASK)
		#map space play/pause
		self.connect("key-press-event", self.on_key_press_event)

		#packing
		self.vbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
		self.hbox=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
		self.hbox.set_margin_start(2)
		self.hbox.set_margin_end(2)
		self.hbox.set_margin_bottom(2)
		self.vbox.pack_start(self.browser, True, True, 0)
		self.vbox.pack_start(self.hbox, False, False, 0)
		self.hbox.pack_start(self.control, False, False, 0)
		self.hbox.pack_start(self.progress, True, True, 10)
		self.hbox.pack_start(self.go_home_button, False, False, 0)
		self.hbox.pack_start(self.search_button, False, False, 0)
		self.hbox.pack_start(self.lyrics_button, False, False, 0)
		if len(self.settings.get_value("profiles")) > 1:
			self.hbox.pack_start(self.profiles, False, False, 0)
		self.hbox.pack_start(self.play_opts, False, False, 0)
		self.hbox.pack_end(menu_button, False, False, 0)

		self.add(self.vbox)

		self.show_all()

	def title_update(self, *args):
		try:
			status=self.client.status()
			if status["songid"] == None:
				self.set_title("mpdevil")
			else:
				song=self.client.currentsong()
				if song["file"] != self.song_file:
					self.set_title(song["artist"]+" - "+song["title"]+" - "+song["album"])
					if self.settings.get_boolean("send-notify"):
						if not self.is_active() and status["state"] == "play":
							notify=Notify.Notification.new(song["title"], song["artist"]+"\n"+song["album"])
							pixbuf=Cover(client=self.client, lib_path=self.settings.get_value("paths")[self.settings.get_int("active-profile")], song_file=song["file"]).get_pixbuf(400)
							notify.set_image_from_pixbuf(pixbuf)
							notify.show()
					self.song_file=song["file"]
		except:
			self.set_title("mpdevil")

	def on_reconnected(self, *args):
		self.client.try_connect_default()
		self.progress.set_sensitive(True)
		self.control.set_sensitive(True)
		self.play_opts.set_sensitive(True)
		self.go_home_button.set_sensitive(True)
		self.search_button.set_sensitive(True)
		self.lyrics_button.set_sensitive(True)
		self.emitter.emit("playlist")
		self.emitter.emit("player")
		self.emitter.emit("options")
		self.emitter.emit("mixer")
		self.emitter.emit("update")
		self.browser.go_home()

	def on_disconnected(self, *args):
		self.lyrics_button.set_active(False)
		self.search_button.set_active(False)
		self.set_title("mpdevil (not connected)")
		self.songid_playing=None
		self.browser.clear()
		self.progress.set_sensitive(False)
		self.control.set_sensitive(False)
		self.play_opts.set_sensitive(False)
		self.go_home_button.set_sensitive(False)
		self.search_button.set_sensitive(False)
		self.lyrics_button.set_sensitive(False)

	def on_search_toggled(self, widget):
		if widget.get_active():
			if self.client.connected():
				def set_active(*args):
					self.search_button.set_active(False)
				self.search_win = SearchWindow(self.client)
				self.search_win.connect("destroy", set_active)
		else:
			self.search_win.destroy()

	def on_lyrics_toggled(self, widget):
		if widget.get_active():
			if self.client.connected():
				def set_active(*args):
					self.lyrics_button.set_active(False)
				self.lyrics_win = LyricsWindow(self.client, self.settings, self.emitter)
				self.lyrics_win.connect("destroy", set_active)
		else:
			self.lyrics_win.destroy()

	def on_key_press_event(self, widget, event):
		if event.keyval == 32: #space
			self.control.play_button.grab_focus()
		if event.keyval == 269025044: #AudioPlay
			self.control.play_button.emit("clicked")
		elif event.keyval == 269025047 or event.keyval == 43 or event.keyval == 65451: #AudioNext
			self.control.next_button.emit("clicked")
		elif event.keyval == 269025046 or event.keyval == 45 or event.keyval == 65453: #AudioPrev
			self.control.prev_button.emit("clicked")
		elif event.keyval == 65307: #esc
			self.go_home_button.emit("clicked")
		elif event.keyval == 65450: #*
			self.progress.seek_forward()
		elif event.keyval == 65455: #/
			self.progress.seek_backward()

	def on_save(self, action, param):
		size=self.get_size()
		self.settings.set_int("width", size[0])
		self.settings.set_int("height", size[1])
		self.browser.save_settings()

	def on_settings(self, action, param):
		settings = SettingsDialog(self, self.settings)
		settings.run()
		settings.destroy()

	def on_stats(self, action, param):
		if self.client.connected():
			stats = ServerStats(self, self.client)
			stats.run()
			stats.destroy()

	def on_update(self, action, param):
		if self.client.connected():
			self.client.update()

	def on_settings_changed(self, *args):
		self.hbox.remove(self.profiles)
		if len(self.settings.get_value("profiles")) > 1:
			self.hbox.pack_start(self.profiles, False, False, 0)
			self.hbox.reorder_child(self.profiles, 5)
			self.profiles.show()

class mpdevil(Gtk.Application):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, application_id="org.mpdevil", flags=Gio.ApplicationFlags.FLAGS_NONE, **kwargs)
		self.settings = Settings()
		self.client=Client(self.settings)
		self.emitter=MpdEventEmitter(self.settings)
		self.window=None

	def do_activate(self):
		if not self.window: #allow just one instance
			self.window = MainWindow(self, self.client, self.settings, self.emitter)
			self.window.connect("delete-event", self.on_delete_event)
		self.window.present()

	def do_startup(self):
		Gtk.Application.do_startup(self)

		action = Gio.SimpleAction.new("about", None)
		action.connect("activate", self.on_about)
		self.add_action(action)

		action = Gio.SimpleAction.new("quit", None)
		action.connect("activate", self.on_quit)
		self.add_action(action)

	def on_delete_event(self, *args):
		if self.settings.get_boolean("stop-on-quit") and self.client.connected():
			self.client.stop()
		self.quit()

	def on_about(self, action, param):
		dialog=Gtk.AboutDialog(transient_for=self.window, modal=True)
		dialog.set_program_name(NAME)
		dialog.set_version(VERSION)
		dialog.set_comments(_("A small MPD client written in python"))
		dialog.set_authors(["Martin Wagner"])
		dialog.set_website("https://github.com/SoongNoonien/mpdevil")
		dialog.set_copyright("\xa9 2020 Martin Wagner")
		dialog.set_logo_icon_name(PACKAGE)
		dialog.run()
		dialog.destroy()

	def on_quit(self, action, param):
		if self.settings.get_boolean("stop-on-quit") and self.client.connected():
			self.client.stop()
		self.quit()

if __name__ == '__main__':
	app = mpdevil()
	app.run(sys.argv)

