/*
Terminology:

min/max slide width : Defines the threshold for allowable widths of the slides. If they get too
                      narrow or too wide, the carousel is resized.

gutter width        : Defines the gap between slides at load. Can change slightly when carousel
                      flexes in width after load.

Teaser              : If there are n (where n >= 3) slides visible in a set of slides with length
                      'count', this option:
                      - if circular, moves slides[count] to be slides[0]
                      - chops off the first half of slides[0] and the last half of of slides[n] by
                        shifting the slider to the left by half a slide width
                      - places the arrows between slides[0] & slides[count] & slides[n-1] & slides[n]

Circular            : By default, the next/previous arrows are disabled if there are no more slides
                      to navigate to. If there are more slides than can be be displayed at once, this
                      option forces the next/previous arrows to always navigate to more slides. Also,
                      if a set of slides does not divide evenly into n groups, this option fills
                      the remaining slots with duplicate slides

n                   : For any given width of the carousel, n is the maximum number of
                      _whole_ slides visible.

j                   : Index of the currently visible slide in slot "1"

Scenario [A]        : count <= n
                      1+ slides visible, no arrows
                      { [1]   [2] }

Scenario [B]        : count > n && ( n < 3 || !teaser )
                      1+ slides visible, arrows
                      { < [1]   [2] > }

Scenario [C]        : count > n && n >= 3 && teaser
                      3+ (whole) slides visible, arrows, teaser
                      {4] < [1]   [2] > [3}

*/

; (function ($, window, undefined) {
	'use strict';

	var DEBUG = false;
	var diag = function (msg) {
		if (DEBUG && window.console) {
			window.console.log('[ AdaptiveCarousel ] ' + msg);
		}
	};

	// Create the defaults once
	var pluginName = "adaptiveCarousel",
		defaults = {
			// Defaults
			minSlideWidth: 180, // in px
			maxSlideWidth: 300, // in px
			gutterWidth: 40,  // in px
			transitionTiming: 500, // in ms
			easeMethod: 'easeInOutExpo', // Choose from: http://easings.net/ or http://gsgd.co.uk/sandbox/jquery/easing/
			teaser: false, // See Terminology
			circular: false  // See Terminology
		};


	// The actual plugin constructor
	function AdaptiveCarousel(options, element) {
		var self = this;

		this.element = element;
		this._defaults = defaults;
		this._name = pluginName;
		this.settings = $.extend({}, defaults, options);

		this.$carousel = $(this.element);
		this.$window = self.$carousel.find('.cpWindow');
		this.$slider = self.$carousel.find('.cpSlider');
		this.slides = self.$slider.find('li');
		this.$firstSlide = self.$slider.find('li:first-child');
		this.count = self.slides.length;
		this.origCount = self.count;
		this.n = 0;
		this.j = 0;

		// Label the original slides on first run
		for (var i = 0; i < self.count; i++) {
			$(self.slides[i]).addClass('slide' + i);
		}

		// Initialize
		this.init();

		this.$carousel.delegate('.arrow', 'click', function (e) {
			e.preventDefault();
			diag('Before moving, j = ' + self.j);
			if ($(this).hasClass('prev')) {
				self.moveBack();
			} else if ($(this).hasClass('next')) {
				self.moveForward();
			}
			diag('After moving, j = ' + self.j);
		});

		//Support swiping if framework is already loaded. Otherwise, it should take care on invoke after it is loaded (use: window.Pages.rwdReady)
		if (typeof ($$) !== 'undefined' && self.$carousel.attr('id')) {
			$$('#' + self.$carousel.attr('id')).on('swipeRight', function (e, a) {
				self.adaptiveCarousel("moveBack");
			});
			$$('#' + self.$carousel.attr('id')).on('swipeLeft', function (e) {
				self.adaptiveCarousel("moveForward");
			});
		}

		// Recalculate the number of slides displayed on window resize
		$(window).smartresize(function () {
			self.onResize();
		});
	}

	AdaptiveCarousel.prototype = {
		init: function () {

			// local variables
			var self = this;

			self.n = findN();
			sizeTheSlides(whichScenario());

			if (!self.settings.circular)
				self.setArrowState();

			self.initImageNextAndPrev();

			// Finding the appropriate number of slides to display at one time
			function findN() {
				var n = 0;
				if (self.$window.width() >= (self.settings.minSlideWidth + self.settings.gutterWidth)) {
					var carouselWidth = self.$carousel.width();
					n = Math.floor((carouselWidth - self.settings.gutterWidth - self.settings.minSlideWidth) / (self.settings.gutterWidth + self.settings.minSlideWidth));
				}
				return n > 0 ? n : 1;
			}

			// Determining which of the three scenarios (see Terminology) the carousel fits
			function whichScenario() {
				diag('n = ' + self.n);
				if (self.count <= self.n) {
					return 'A';
				} else {
					if (self.n < 3 || !self.settings.teaser) {
						return 'B';
					} else {
						return 'C';
					}
				}
			}

			// The heart of the script
			function sizeTheSlides(scenario) {
				/* Note: This may seem like excessive if statements, but the scenarios make it more clear
						 and many of these operation must occur in a specific order.
				*/

				var carouselWidth = self.$carousel.width();
				var sliderWidth;
				if (scenario === 'A') {
					diag('Fits [A]');
					sliderWidth = carouselWidth;
				} else {
					if (scenario === 'B') {
						diag('Fits [B]');
						// Make sure there's room for the arrow (gutterWidth) on either side of the first/last
						// visible slides
						var windowMargin;
						//The value below is based on pure trial/error to fix an issue with IE in cotext to carousel display
						//https://system.netsuite.com/app/crm/support/issuedb/issue.nl?id=3211942&l=T
						//IE basically rounds up the math calculations to 2 decimal places causing some display issues.
						//Adding the error correction value gives the carousel arrows enough space to display right and not overlap
						//the images.
						var ieErrorCorrectionValue = .0095;
						if (/(?:\b(MS)?IE\s+|\bTrident\/7\.0;.*\s+rv:)(\d+)/.test(navigator.userAgent)) {
							windowMargin = (((self.settings.gutterWidth / (2 * carouselWidth))) + ieErrorCorrectionValue) * 100;
						} else {
							windowMargin = ((self.settings.gutterWidth / (2 * carouselWidth))) * 100;
						}
						self.$window.css({
							margin: '0 ' + windowMargin + '%',
							width: (100 - windowMargin * 2) + '%'
						});
					}

					diag('Fits [B] or [C]');
					sliderWidth = self.$slider.width();
				}

				var margin = (self.settings.gutterWidth / sliderWidth) * 100;

				if (scenario === 'B' || scenario === 'C') {
					diag('Fits [B] or [C]');
					if (self.settings.circular) {
						diag('is circular');

						// Make clones
						var startClones = self.slides.slice(self.count - self.n, self.count).clone().addClass('clone'),
							endClones = self.slides.slice(0, self.n).clone().addClass('clone');

						// Attach clones
						self.$slider.prepend(startClones);
						self.$slider.append(endClones);

						// Adjust starting position and count
						self.j = self.n;
						self.slides = self.$slider.find('li');
						self.count = self.slides.length;
					}

					// Adjust margin to be relative to n/count
					margin = margin * (self.n / self.count);

					// Adjust slider to hold slides in a row
					self.$slider.width(self.count * (100 / self.n) + '%');
					sliderWidth = self.$slider.width();

					/* Couldn't quite figure this out
					if ( Modernizr.csstransitions ) {
						self.$window.before('<style>.js .animated .cpSlider { -webkit-transition-duration: ' + self.settings.transitionTiming + 'ms; transition-duration: ' + self.settings.transitionTiming + 'ms; }</style>');
						self.$carousel.addClass('animated');
					}
					*/
					self.$window.after('<a href="#" class="arrow next"><span class="visuallyHidden">Next</span></a><a href="#" class="arrow prev"><span class="visuallyHidden">Previous</span></a>');
				}

				if (scenario === 'A' || scenario === 'B') {

					diag('Fits [A] or [B]');

					var slideWidth = (100 - self.count * margin) / self.count;
					self.slides.outerWidth(slideWidth + '%');

					var firstSlideWidth = self.$firstSlide.outerWidth();

					if (firstSlideWidth > self.settings.maxSlideWidth || firstSlideWidth < self.settings.minSlideWidth) {
						if (firstSlideWidth > self.settings.maxSlideWidth) {
							diag('Slides too wide');
							slideWidth = (self.settings.maxSlideWidth / sliderWidth) * 100;
						} else {
							diag('Slides too narrow');
							//Only enforce minimum width if margins wouldn't become negative
							//Formula is PossibleNewMargin = (100 - self.count * PossibleNewSlideWidth) / self.count
							if (((100 - self.count * ((self.settings.minSlideWidth / sliderWidth) * 100)) / self.count) > 0) {
								slideWidth = (self.settings.minSlideWidth / sliderWidth) * 100;
							}
						}
						self.slides.outerWidth(slideWidth + '%');
						margin = (100 - self.count * slideWidth) / self.count;
					}

					if (scenario === 'B') {
						diag('Fits [B]');
						self.moveTheSlides('dir', 0);
						self.$carousel.find('.arrow').width((self.settings.gutterWidth / carouselWidth) * 100 + '%');
					}

				} else {
					diag('Fits [C]');
					self.slides.outerWidth((100 - self.count * margin) / self.count + '%');
					self.$carousel.addClass('teaser');
					self.moveTheSlides('dir', 0);
					self.$carousel.find('.arrow').width(((self.$firstSlide.outerWidth() / 2 + self.settings.gutterWidth / 2) / carouselWidth) * 100 + '%');
				}

				self.slides.css('margin', '0 ' + margin / 2 + '%');
			}
		},
		moveTheSlides: function (dir, speed) {

			var self = this,
				m = self.n,
				offset = 0;
			if (self.$carousel.hasClass('teaser')) {
				m--;
				offset = 0.5;
			}

			if (dir === 'back') {
				self.j = self.j - m;
				if (!self.settings.circular && self.j < 0) {
					self.j = 0;
				}
			} else if (dir === 'forward') {
				self.j = self.j + m;
				if (!self.settings.circular && self.j > (self.count - m)) {
					self.j = self.count - m;
				}
			}

			var left = (-self.j + offset) * (100 / self.n);

			/* Couldn't quite figure this out
			if ( !Modernizr.csstransitions ) {
			*/

			self.$slider.animate({
				left: left + '%',
			}, speed, self.settings.easeMethod);
			/* Couldn't quite figure this out
		} else {

			if ( speed === 0 ) {
				self.$carousel.removeClass('animated');
			}
				self.$slider.css('left', left + '%');
				if ( speed === 0 ) {
					setTimeout( function() { self.$carousel.addClass('animated') }, self.settings.transitionTiming );
				}
		}
		*/

			if (dir === 'forward' || dir === 'back') {
				if (self.settings.circular) {

					// Checking to see if we're past the beginning or end of a circular carousel
					if ((self.j < self.n) || (self.j > self.origCount)) {

						if (self.j < self.n) {
							diag("We're past the beginning");
							self.j = self.j + self.origCount;
						} else {
							diag("We're past the end");
							self.j = self.j - self.origCount;
						}

						// Switch to non-cloned position, instantly, after a delay equal to transition time
						setTimeout(self.moveTheSlides('dir', 0), self.settings.transitionTiming);
					}
				} else {
					diag('Set arrow state after movement');
					self.setArrowState();
				}
			}

			self.initImageNextAndPrev();

			return self.j;

		},
		// Sometimes the arrows need to enabled/disabled
		setArrowState: function () {
			var self = this;
			self.$carousel.find('.arrow').removeClass('disabled');
			if (self.j === 0) {
				self.$carousel.find('.arrow.prev').addClass('disabled');
			} else if (self.j >= (self.count - self.n)) {
				self.$carousel.find('.arrow.next').addClass('disabled');
			}
		},
		onResize: function () {
			var self = this;
			if (self.$firstSlide.outerWidth() < self.settings.minSlideWidth || self.$firstSlide.outerWidth() >= self.settings.maxSlideWidth) {
				diag('Resize!');

				// Resetting things back to a fresh, known state for calculations
				self.$window.css({
					margin: '0',
					width: '100%'
				});
				self.$slider.css({
					left: '0',
					width: '100%'
				});

				self.$carousel.removeClass('teaser');
				self.$carousel.find('.clone').remove();
				self.$carousel.find('.arrow').remove();
				self.slides = self.$slider.find('li');
				self.count = self.origCount;

				// Re-initialize
				self.init();
			}
		},
		moveForward: function () {
			var self = this;
			if (self.$carousel.find('a.arrow.next').length == 1)
				self.moveTheSlides('forward', self.settings.transitionTiming);
		},
		moveBack: function () {
			var self = this;
			if (self.$carousel.find('a.arrow.prev').length == 1)
				self.moveTheSlides('back', self.settings.transitionTiming);
		},
		initImageNextAndPrev: function () {
			var self = this;

			var loadImage = function (widgetItem) {
				var image = $(widgetItem).find('img');

				if (image.length !== 0) {
					var $this = $(image),
						delayLoadUrl = $this.attr('data-delay-load'),
						imgSrc = $this.attr('src');

					if (delayLoadUrl !== imgSrc) {
						if (delayLoadUrl !== undefined && delayLoadUrl !== '' && delayLoadUrl !== null) {
							$this.attr('src', delayLoadUrl);
							$this.removeAttr('data-delay-load');
						}
					}
				}
			};

			if ($("img[data-delay-load]", self.element).length > 0) {
				var $widgetItems = $("li.widgetItem", self.element);

				for (var i = 0; i <= self.n; i++) {
					var forward = self.j + i;

					if (forward > $widgetItems.length) {
						var diff = forward - $widgetItems.length;
						loadImage($widgetItems[diff]);
					}
					else {
						loadImage($widgetItems[forward]);
					}

					if (self.settings.circular) {
						var backward = self.j - i;

						if (backward < 0) {
							var diff = $widgetItems.length + backward;
							loadImage($widgetItems[diff]);
						}
						else {
							loadImage($widgetItems[backward]);
						}
					}
				}
			}
		}
	};

	/* jQuery Plugin Support */
	$.fn.adaptiveCarousel = function (options) {
		if (typeof options === 'string') {
			var args = Array.prototype.slice.call(arguments, 1);
			this.each(function () {
				var instance = $.data(this, 'adaptiveCarousel');
				if (!instance) {
					diag("cannot call methods on adaptiveCarousel prior to initialization; " +
						"attempted to call method '" + options + "'");
					return;
				}
				if (!$.isFunction(instance[options]) || options.charAt(0) === "_") {
					diag("no such method '" + options + "' for adaptiveCarousel instance");
					return;
				}
				instance[options].apply(instance, args);
			});
		}
		else {
			this.each(function () {
				var instance = $.data(this, 'adaptiveCarousel');
				if (instance) {
					instance.init(options);
				}
				else {
					instance = $.data(this, 'adaptiveCarousel', new AdaptiveCarousel(options, this));
				}
			});
		}

		return this;
	};

})(jQuery, window);

(function ($, sr) {

	// debouncing function from John Hann
	// http://unscriptable.com/index.php/2009/03/20/debouncing-javascript-methods/
	var debounce = function (func, threshold, execAsap) {
		var timeout;

		return function debounced() {
			var obj = this, args = arguments;
			function delayed() {
				if (!execAsap)
					func.apply(obj, args);
				timeout = null;
			};

			if (timeout)
				clearTimeout(timeout);
			else if (execAsap)
				func.apply(obj, args);

			timeout = setTimeout(delayed, threshold || 100);
		};
	};
	// smartresize
	jQuery.fn[sr] = function (fn) { return fn ? this.bind('resize', debounce(fn)) : this.trigger(sr); };

})(jQuery, 'smartresize');
