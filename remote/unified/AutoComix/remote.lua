local keyboard = libs.keyboard;
local win = libs.win;

-- AutoComix must have focus for the keys to arrive (the second screen's window never takes focus).
local function key(...)
	pcall(function () win.switchtowait("AutoComix.exe"); end);
	keyboard.stroke(...);
end

--@help Start AutoComix
actions.launch = function ()
	os.start("@@EXE@@");  -- installera_unified_remote.ps1 writes in the path
end

-- Reading
--@help Next panel/page
actions.next = function () key("space"); end
--@help Previous panel/page
actions.prev = function () key("back"); end
--@help Next page
actions.next_page = function () key("next"); end
--@help Previous page
actions.prev_page = function () key("prior"); end
--@help First page
actions.first = function () key("home"); end
--@help Last page
actions.last = function () key("end"); end
--@help Next file
actions.next_file = function () key("n"); end
--@help Previous file
actions.prev_file = function () key("b"); end
--@help Last comic (Ctrl+L)
actions.resume = function () key("control", "l"); end

-- Slideshow
--@help Slideshow on/off
actions.slideshow = function () key("s"); end
--@help Longer time per step
actions.slide_longer = function () key("menu", "up"); end
--@help Shorter time per step
actions.slide_shorter = function () key("menu", "down"); end
--@help Animation pause/play
actions.anim = function () key("p"); end

-- Display
--@help Guided mode (panel by panel) on/off
actions.guided = function () key("g"); end
--@help Whole page before the panels on/off
actions.overview = function () key("v"); end
--@help Full screen
actions.fullscreen = function () key("f"); end
--@help Distance mode
actions.distance = function () key("shift", "f"); end
--@help Second screen: off/mirror/distribution
actions.second = function () key("f9"); end
--@help Second screen fit
actions.second_fit = function () key("shift", "f9"); end
--@help Zoom in
actions.zoom_in = function () key("control", "oem_plus"); end
--@help Zoom out
actions.zoom_out = function () key("control", "oem_minus"); end
--@help Reset zoom
actions.zoom_reset = function () key("0"); end
--@help Leave full screen / close help
actions.escape = function () key("escape"); end
