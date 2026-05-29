function openCalendarPublicSubmissionModal (calendarID, eventID, isCopy, order, updatePanelID, isSubmit) {
	var title = null;
	var className = null;

	if (isSubmit) {
		title = ' Event Submission';
		className = 'submitEvent';
	} else
		className = 'liveEdit calendar';

	var url = '/common/modules/Calendar/calendarLiveEdit.aspx?calendarID=' + calendarID + '&eventID=' + eventID + '&order=' + order + '&updatePanelID=' + updatePanelID;

	if (isSubmit)
		url = url + '&submit=1';
	if (isCopy)
		url = url + '&strPage=itemCopy';
	else
		url = url + '&strPage=itemForm';

	openCpModal({
		title: title,
		className: className,
		isFrontEnd: true,
		useIframe: true,
		draggable: true,
		url: url
	});
}

function openCalendarIcalEventDetailsModal(startTime, endTime, location, description) {
	var title = "Event Details";
	var className = 'modalContainer MVC iCalEventDetailsModal';


	var timeDiv ;
	var start = new Date(startTime);
	var end = new Date(endTime);

	var startDay = (start).toLocaleDateString(undefined, { month: 'long', day: 'numeric' });
	var endDay = (end).toLocaleDateString(undefined, { month: 'long', day: 'numeric' });

	var dateDiv = startDay === endDay ? `${startDay}` : `<span> ${startDay}  —  ${endDay} </span>`;

	if (start.getHours() == 0 && start.getMinutes() == 0) {
		timeDiv = "All Day";
	} else {
		timeDiv = start.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) + " - " + end.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
	}
	
	
	var htmlContent =
		'<div id="calendarIcalEventDetailsModal"><ol class= "cpForm" ><li class="left"><div class="label">Date</div><div id="dateDiv">' +
			dateDiv +
			'</div></li><li class="left"><div class="label">Time</div><div id="timeDiv">' +
		timeDiv + '</div></li>';

	if (location) {
		htmlContent += '<li class="left location"><div class="label">Location</div><div id="locationDiv"> ' +
			location +
			'</div></li>';
	}
	if (description) {
		htmlContent += '<li class="left description"><div class="label">Description</div><div class="icalDescription" id="icalDescription">' +
			description +
			'</div></li></ol></div >';
	}

	openCpModal({
		title: title,
		className: className,
		htmlContent: htmlContent,
		elementID: 'calendarIcalEventDetailsModal',
		isFrontEnd: true,
		draggable: true,
		async: false
	});
	function daysIntoYear(date) {
		return (Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - Date.UTC(date.getFullYear(), 0, 0)) / 24 / 60 / 60 / 1000;
	}
	$('div.icalDescription').urlToLink({ target: '_blank' });
}
