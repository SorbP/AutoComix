local keyboard = libs.keyboard;
local win = libs.win;

-- AutoComix måste ha fokus för att tangenterna ska nå fram (andra skärmens fönster tar aldrig fokus).
local function key(...)
	pcall(function () win.switchtowait("AutoComix.exe"); end);
	keyboard.stroke(...);
end

--@help Starta AutoComix
actions.launch = function ()
	os.start("D:\\ClaudeBox\\PanelView\\dist\\windows\\AutoComix\\AutoComix.exe");
end

-- Läsa
--@help Nästa ruta/sida
actions.next = function () key("space"); end
--@help Föregående ruta/sida
actions.prev = function () key("back"); end
--@help Nästa sida
actions.next_page = function () key("next"); end
--@help Föregående sida
actions.prev_page = function () key("prior"); end
--@help Första sidan
actions.first = function () key("home"); end
--@help Sista sidan
actions.last = function () key("end"); end
--@help Nästa fil
actions.next_file = function () key("n"); end
--@help Föregående fil
actions.prev_file = function () key("b"); end
--@help Senaste serien (Ctrl+L)
actions.resume = function () key("control", "l"); end

-- Bildspel
--@help Bildspel på/av
actions.slideshow = function () key("s"); end
--@help Längre tid per steg
actions.slide_longer = function () key("menu", "up"); end
--@help Kortare tid per steg
actions.slide_shorter = function () key("menu", "down"); end
--@help Animation paus/spela
actions.anim = function () key("p"); end

-- Visning
--@help Guidat läge (ruta för ruta) på/av
actions.guided = function () key("g"); end
--@help Hela sidan före rutorna på/av
actions.overview = function () key("v"); end
--@help Helskärm
actions.fullscreen = function () key("f"); end
--@help Avståndsläge
actions.distance = function () key("shift", "f"); end
--@help Andra skärmen: av/spegling/fördelning
actions.second = function () key("f9"); end
--@help Andra skärmens anpassning
actions.second_fit = function () key("shift", "f9"); end
--@help Zooma in
actions.zoom_in = function () key("control", "oem_plus"); end
--@help Zooma ut
actions.zoom_out = function () key("control", "oem_minus"); end
--@help Återställ zoom
actions.zoom_reset = function () key("0"); end
--@help Lämna helskärm / stäng hjälp
actions.escape = function () key("escape"); end
