var MiniCalendar = function () {
	var self = this;
	var $calendar = null;
	var $nextButton = null;
	var $prevButton = null;
	var widgetId = null;
	var contentContainerID = null;
	var currentMonth = null;
	var todayMonth = null;
	var preventNavigationOnArrows;
	var urlChangeMonth = '/Calendar/WidgetGet/ChangeMiniCalendarMonth';
	var urlUpdateList = '/Calendar/WidgetGet/UpdateList';

	function announceMonthChange(monthDate) {
		var monthName = monthDate.toLocaleString('default', { month: 'long', year: 'numeric' });
		var $announcement = $calendar.find('#miniCalendarAnnouncement' + widgetId);
		// Clear then set to ensure aria-live fires even if the same month is somehow set
		$announcement.text('');
		setTimeout(function () {
			$announcement.text(monthName);
		}, 50);
	}

	function restoreFocusAfterMonthChange(navigatedForward) {
		// Determine which button should receive focus based on whether prev is now disabled
		if (isCurrentMonthTodayMonth()) {
			// Prev is disabled — focus next
			$nextButton.focus();
		} else if (navigatedForward) {
			$nextButton.focus();
		} else {
			$prevButton.focus();
		}
	}

	function moveMonth(monthDate, navigatedForward) {
		var miniCalendarResult;
		var eventListResult;
		var async1 = $.ajax({
			type: 'POST',
			url: urlChangeMonth,
			data: JSON.stringify({
				"month": monthDate.getMonth() + 1,
				"year": monthDate.getFullYear(),
				"pageID": $('#pagePageID').val(),
				"widgetID": widgetId,
				"contentContainerID": contentContainerID,
				"moduleID": $('#pageModuleID').val()
			}),
			contentType: 'application/json',
			cache: false,
			async: true,
			success: function (response) {
				miniCalendarResult = response;
			},
			error: function (xhr, textStatus, exception) {
				alert('Error: ' + xhr.statusText + '\nStatus: ' + xhr.status);
			}
		});
		var async2 = $.ajax({
			type: 'POST',
			url: urlUpdateList,
			data: JSON.stringify({
				"month": monthDate.getMonth() + 1,
				"year": monthDate.getFullYear(),
				"pageID": $('#pagePageID').val(),
				"widgetID": widgetId,
				"contentContainerID": contentContainerID,
				"moduleID": $('#pageModuleID').val()
			}),
			contentType: 'application/json',
			cache: false,
			async: true,
			success: function (response) {
				eventListResult = response;
			},
			error: function (xhr, textStatus, exception) {
				alert('Error: ' + xhr.statusText + '\nStatus: ' + xhr.status);
			}
		});
		$.when(async1, async2).done(function () {
			currentMonth = monthDate;
			$calendar.find('div[data-minicalendar]').replaceWith(miniCalendarResult);
			initButtons();
			$calendar.find('div.row').html(eventListResult);
			// Announce the new month to screen readers
			announceMonthChange(monthDate);
			// Restore focus to the correct button (WCAG 2.4.3)
			restoreFocusAfterMonthChange(navigatedForward);
		});
	};

	function initButtons() {
		$nextButton = $calendar.find("button.cp-miniCalendar-arrow--right");
		$nextButton.click(function (e) {
			if (preventNavigationOnArrows) {
				e.preventDefault();
			} else {
				self.moveNextMonth();
			}
		});
		$prevButton = $calendar.find("button.cp-miniCalendar-arrow--left");
		if (isCurrentMonthTodayMonth()) {
			$prevButton.prop("disabled", true);
		} else {
			$prevButton.click(function () {
				if (preventNavigationOnArrows) {
					e.preventDefault();
				} else {
					self.movePrevMonth();
				}
			});
		}
	}

	function isCurrentMonthTodayMonth() {
		return (todayMonth.getMonth() === currentMonth.getMonth() && todayMonth.getFullYear() === currentMonth.getFullYear());
	}

	this.moveNextMonth = function () {
		var nextMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1);
		moveMonth(nextMonth, true);
	};

	this.movePrevMonth = function () {
		if (!isCurrentMonthTodayMonth()) {
			var prevMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1);
			moveMonth(prevMonth, false);
		}
	};

	const focusCell = (event, current, focusables, index) => {
		event.preventDefault();
		if (index >= 0 && index < focusables.length) {
			const next = focusables[index];
			current.tabIndex = "-1";
			next.tabIndex = "0";
			next.focus();
			return true
		}
		return false;
	}

	const itemPos = (item)=> {
		const x = item.parentNode.cellIndex;
		const y = item.parentNode.parentNode.rowIndex - 1;
		return [x, y];
	}

	const processKeydown = (e) => {
		const widget = e.currentTarget;
		const tbody = widget.querySelector('.miniCalendar tbody');
		const focusables = [...tbody.querySelectorAll("a")];
		const currentFocused = e.target.closest("a");
		const currentIdx = focusables.indexOf(currentFocused);
		const [currentCellIdx, currentRowIdx] = itemPos(currentFocused);
		switch (e.key) {
			case "ArrowRight":
				focusCell(e, currentFocused, focusables, currentIdx + 1)
				break;
			case "ArrowLeft":
				focusCell(e, currentFocused, focusables, currentIdx - 1)
				break;
			case "ArrowDown":
				const nextSameCellIdx = focusables.findIndex((item, idx) => {
					const [x, _] = itemPos(item);
					return idx > currentIdx && x === currentCellIdx;
				});
				focusCell(e, currentFocused, focusables, nextSameCellIdx);
				break;
			case "ArrowUp":
				const prevSameCellIdx = focusables.findLastIndex((item, idx) => {
					const [x, _] = itemPos(item);
					return idx < currentIdx && x === currentCellIdx;
				});
				focusCell(e, currentFocused, focusables, prevSameCellIdx);
				break;
			case "End":
				if (e.ctrlKey) {
					focusCell(e, currentFocused, focusables, focusables.length - 1)
					break;
				} else {
					const lastInSameRow = focusables.findLastIndex((item, idx) => {
						const [_, y] = itemPos(item);
						return idx > currentIdx && y === currentRowIdx;
					});
					focusCell(e, currentFocused, focusables, lastInSameRow);
					break;
				}
			case "Home":
				if (e.ctrlKey) {
					focusCell(e, currentFocused, focusables, 0)
					break;
				} else {
					const firstInSameRow = focusables.findIndex((item, idx) => {
						const [_, y] = itemPos(item);
						return idx < currentIdx && y === currentRowIdx;
					});
					focusCell(e, currentFocused, focusables, firstInSameRow);
					break;
				}
		}
	};


	this.init = function (options) {
		widgetId = options.widgetId;
		preventNavigationOnArrows = options.preventNavigationOnArrows;
		$calendar = $("#widgetCalendar" + widgetId);
		$calendar[0].addEventListener("keydown", processKeydown);
		var $pageContent = $calendar.parents('.pageContent').filter(":first");
		contentContainerID = $pageContent.data('containerid');
		var $monthToRender = $calendar.find('input[name="monthToRender"]');
		var month = parseInt($monthToRender.data("month"), 10);
		var year = parseInt($monthToRender.data("year"), 10);
		currentMonth = new Date(year, month - 1, 1);
		var now = new Date();
		todayMonth = new Date(now.getFullYear(), now.getMonth(), 1);
		initButtons();
	};

};
