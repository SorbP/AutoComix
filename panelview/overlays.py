"""Överlägg på visningsytan som i CDisplayEx: miniatyrlist (Ctrl+T) och sidreglage (Ctrl+I)."""
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSlider, QWidget

THUMB = 150


class _Sig(QObject):
    done = Signal(object, int, QImage)  # serie, sida, miniatyr


class _Thumb(QRunnable):
    def __init__(self, comic, i, sig):
        super().__init__()
        self.comic, self.i, self.sig = comic, i, sig

    def run(self):
        try:
            img = QImage.fromData(self.comic.read(self.i)).scaled(
                THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        except Exception:
            img = QImage()
        try:
            self.sig.done.emit(self.comic, self.i, img)
        except RuntimeError:
            pass


class ThumbBar(QListWidget):
    """Horisontell miniatyrlist längst ner. Pilar flyttar markeringen, Enter/klick hoppar till sidan."""
    picked = Signal(int, bool)  # sida, stäng listan

    def __init__(self, parent):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 14, THUMB + 30))
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setFixedHeight(THUMB + 52)
        self.setStyleSheet("QListWidget{background:rgba(10,10,10,225);color:#ddd;border:none;}"
                           "QListWidget::item:selected{background:rgba(90,160,255,120);}")
        self.comic = None
        self.pix = {}
        self.sig = _Sig(self)
        self.sig.done.connect(self._done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.itemClicked.connect(lambda it: self.picked.emit(it.data(Qt.ItemDataRole.UserRole), False))
        self.itemActivated.connect(lambda it: self.picked.emit(it.data(Qt.ItemDataRole.UserRole), True))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # tangenterna fortsätter styra läsningen medan listan är öppen
        self.hide()

    def set_comic(self, comic, rtl):
        if comic is not self.comic:
            self.pool.clear()
            self.comic, self.pix = comic, {}
            self.clear()
            if comic is None:
                return
            ph = QPixmap(THUMB, THUMB)
            ph.fill(QColor(45, 45, 45))
            for i in range(len(comic.pages)):
                it = QListWidgetItem(QIcon(ph), str(i + 1))
                it.setData(Qt.ItemDataRole.UserRole, i)
                self.addItem(it)
            self._queued = False
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)

    def show_at(self, page):
        if self.comic is None:
            return
        if not self._queued:  # ladda miniatyrer närmast aktuell sida först
            self._queued = True
            for i in sorted(range(len(self.comic.pages)), key=lambda i: abs(i - page)):
                self.pool.start(_Thumb(self.comic, i, self.sig))
        self.show()
        self.raise_()
        self.select(page)

    def select(self, page):
        if 0 <= page < self.count():
            self.setCurrentRow(page)
            self.scrollToItem(self.item(page), QListWidget.ScrollHint.PositionAtCenter)

    def move_sel(self, d):
        self.select(max(0, min(self.count() - 1, self.currentRow() + d)))

    def _done(self, comic, i, img):
        if comic is self.comic and not img.isNull() and i < self.count():
            self.item(i).setIcon(QIcon(QPixmap.fromImage(img)))

    def shutdown(self):
        self.pool.clear()
        self.pool.waitForDone(2000)


class PageSlider(QWidget):
    """Sidreglage längst ner; drag visar sidnummer, släpp hoppar."""
    picked = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("PageSlider{background:rgba(10,10,10,215);} QLabel{color:#ddd;font-size:13px;}")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.label = QLabel()
        self.label.setMinimumWidth(90)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.addWidget(self.slider)
        lay.addWidget(self.label)
        self.setFixedHeight(44)
        self.slider.valueChanged.connect(lambda val: self.label.setText(f"{val} / {self.slider.maximum()}"))
        self.slider.sliderReleased.connect(lambda: self.picked.emit(self.slider.value() - 1))
        self.slider.actionTriggered.connect(self._clicked)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def _clicked(self, action):
        if not self.slider.isSliderDown():  # klick i spåret / tangent: hoppa direkt
            self.picked.emit(self.slider.sliderPosition() - 1)

    def sync(self, page, n, rtl):
        self.slider.blockSignals(True)
        self.slider.setMaximum(max(1, n))
        self.slider.setValue(page + 1)
        self.slider.setInvertedAppearance(rtl)
        self.slider.blockSignals(False)
        self.label.setText(f"{page + 1} / {n}")
