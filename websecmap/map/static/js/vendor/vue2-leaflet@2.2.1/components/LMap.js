import { setOptions, CRS, map, DomEvent, latLng, latLngBounds } from 'leaflet';

var debounce = function (fn, time) {
  var timeout;

  return function () {
    var args = [], len = arguments.length;
    while ( len-- ) args[ len ] = arguments[ len ];

    var context = this;
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(function () {
      fn.apply(context, args);
      timeout = null;
    }, time);
  };
};

var capitalizeFirstLetter = function (string) {
  if (!string || typeof string.charAt !== 'function') { return string; }
  return string.charAt(0).toUpperCase() + string.slice(1);
};

var propsBinder = function (vueElement, leafletElement, props, options) {
  var loop = function ( key ) {
    var setMethodName = 'set' + capitalizeFirstLetter(key);
    var deepValue = (props[key].type === Object) ||
      (props[key].type === Array) ||
      (Array.isArray(props[key].type));
    if (props[key].custom && vueElement[setMethodName]) {
      vueElement.$watch(key, function (newVal, oldVal) {
        vueElement[setMethodName](newVal, oldVal);
      }, {
        deep: deepValue
      });
    } else if (setMethodName === 'setOptions') {
      vueElement.$watch(key, function (newVal, oldVal) {
        setOptions(leafletElement, newVal);
      }, {
        deep: deepValue
      });
    } else if (leafletElement[setMethodName]) {
      vueElement.$watch(key, function (newVal, oldVal) {
        leafletElement[setMethodName](newVal);
      }, {
        deep: deepValue
      });
    }
  };

  for (var key in props) loop( key );
};

var collectionCleaner = function (options) {
  var result = {};
  for (var key in options) {
    var value = options[key];
    if (value !== null && value !== undefined) {
      result[key] = value;
    }
  }
  return result;
};

var optionsMerger = function (props, instance) {
  var options = instance.options && instance.options.constructor === Object ? instance.options : {};
  props = props && props.constructor === Object ? props : {};
  var result = collectionCleaner(options);
  props = collectionCleaner(props);
  var defaultProps = instance.$options.props;
  for (var key in props) {
    var def = defaultProps[key] ? defaultProps[key].default : Symbol('unique');
    if (result[key] && def !== props[key]) {
      console.warn((key + " props is overriding the value passed in the options props"));
      result[key] = props[key];
    } else if (!result[key]) {
      result[key] = props[key];
    }
  }  return result;
};

var Options = {
  props: {
    options: {
      type: Object,
      default: function () { return ({}); }
    }
  }
};

//

var script = {
  name: 'LMap',
  mixins: [Options],
  props: {
    center: {
      type: [Object, Array],
      custom: true,
      default: function () { return [0, 0]; }
    },
    bounds: {
      type: [Array, Object],
      custom: true,
      default: null
    },
    maxBounds: {
      type: [Array, Object],
      default: null
    },
    zoom: {
      type: Number,
      custom: true,
      default: 0
    },
    minZoom: {
      type: Number,
      default: null
    },
    maxZoom: {
      type: Number,
      default: null
    },
    paddingBottomRight: {
      type: Array,
      custom: true,
      default: null
    },
    paddingTopLeft: {
      type: Array,
      custom: true,
      default: null
    },
    padding: {
      type: Array,
      custom: true,
      default: null
    },
    worldCopyJump: {
      type: Boolean,
      default: false
    },
    crs: {
      type: Object,
      custom: true,
      default: function () { return CRS.EPSG3857; }
    },
    maxBoundsViscosity: {
      type: Number,
      default: null
    },
    inertia: {
      type: Boolean,
      default: null
    },
    inertiaDeceleration: {
      type: Number,
      default: null
    },
    inertiaMaxSpeed: {
      type: Number,
      default: null
    },
    easeLinearity: {
      type: Number,
      default: null
    },
    zoomAnimation: {
      type: Boolean,
      default: null
    },
    zoomAnimationThreshold: {
      type: Number,
      default: null
    },
    fadeAnimation: {
      type: Boolean,
      default: null
    },
    markerZoomAnimation: {
      type: Boolean,
      default: null
    },
    noBlockingAnimations: {
      type: Boolean,
      default: false
    }
  },
  data: function data () {
    return {
      ready: false,
      lastSetCenter: null,
      lastSetBounds: null,
      lastSetZoom: null,
      layerControl: undefined,
      layersToAdd: []
    };
  },
  computed: {
    fitBoundsOptions: function fitBoundsOptions () {
      var options = {};
      if (this.padding) {
        options.padding = this.padding;
      } else {
        if (this.paddingBottomRight) {
          options.paddingBottomRight = this.paddingBottomRight;
        }
        if (this.paddingTopLeft) {
          options.paddingTopLeft = this.paddingTopLeft;
        }
      }
      return options;
    }
  },
  beforeDestroy: function beforeDestroy () {
    if (this.mapObject) {
      this.mapObject.remove();
    }
  },
  mounted: function mounted () {
    var this$1 = this;

    var options = optionsMerger({
      minZoom: this.minZoom,
      maxZoom: this.maxZoom,
      maxBounds: this.maxBounds,
      maxBoundsViscosity: this.maxBoundsViscosity,
      worldCopyJump: this.worldCopyJump,
      crs: this.crs,
      center: this.center,
      zoom: this.zoom,
      inertia: this.inertia,
      inertiaDeceleration: this.inertiaDeceleration,
      inertiaMaxSpeed: this.inertiaMaxSpeed,
      easeLinearity: this.easeLinearity,
      zoomAnimation: this.zoomAnimation,
      zoomAnimationThreshold: this.zoomAnimationThreshold,
      fadeAnimation: this.fadeAnimation,
      markerZoomAnimation: this.markerZoomAnimation
    }, this);
    this.mapObject = map(this.$el, options);
    this.setBounds(this.bounds);
    this.mapObject.on('moveend', debounce(this.moveEndHandler, 100));
    DomEvent.on(this.mapObject, this.$listeners);
    propsBinder(this, this.mapObject, this.$options.props);
    this.ready = true;
    // DEPRECATED leaflet:load
    this.$emit('leaflet:load');
    this.$nextTick(function () {
      this$1.$emit('ready', this$1.mapObject);
    });
  },
  methods: {
    registerLayerControl: function registerLayerControl (lControlLayers) {
      var this$1 = this;

      this.layerControl = lControlLayers;
      this.mapObject.addControl(lControlLayers.mapObject);
      this.layersToAdd.forEach(function (layer) {
        this$1.layerControl.addLayer(layer);
      });
      this.layersToAdd = [];
    },
    addLayer: function addLayer (layer, alreadyAdded) {
      if (layer.layerType !== undefined) {
        if (this.layerControl === undefined) {
          this.layersToAdd.push(layer);
        } else {
          this.layerControl.addLayer(layer);
        }
      }
      if (!alreadyAdded) {
        this.mapObject.addLayer(layer.mapObject);
      }
    },
    removeLayer: function removeLayer (layer, alreadyRemoved) {
      if (layer.layerType !== undefined) {
        if (this.layerControl === undefined) {
          this.layersToAdd = this.layersToAdd.filter(function (l) { return l.name !== layer.name; });
        } else {
          this.layerControl.removeLayer(layer);
        }
      }
      if (!alreadyRemoved) {
        this.mapObject.removeLayer(layer.mapObject);
      }
    },
    setZoom: function setZoom (newVal, oldVal) {
      this.mapObject.setZoom(newVal, {
        animate: !this.noBlockingAnimations ? false : null
      });
    },
    setCenter: function setCenter (newVal, oldVal) {
      if (newVal == null) {
        return;
      }
      var newCenter = latLng(newVal);
      var oldCenter = this.lastSetCenter || this.mapObject.getCenter();
      if (oldCenter.lat !== newCenter.lat ||
        oldCenter.lng !== newCenter.lng) {
        this.lastSetCenter = newCenter;
        this.mapObject.panTo(newCenter, {
          animate: !this.noBlockingAnimations ? false : null
        });
      }
    },
    setBounds: function setBounds (newVal, oldVal) {
      if (!newVal) {
        return;
      }
      var newBounds = latLngBounds(newVal);
      if (!newBounds.isValid()) {
        return;
      }
      var oldBounds = this.lastSetBounds || this.mapObject.getBounds();
      var boundsChanged = !oldBounds.equals(newBounds, 0); // set maxMargin to 0 - check exact equals
      if (boundsChanged) {
        this.lastSetBounds = newBounds;
        this.mapObject.fitBounds(newBounds, this.fitBoundsOptions);
      }
    },
    setPaddingBottomRight: function setPaddingBottomRight (newVal, oldVal) {
      this.paddingBottomRight = newVal;
    },
    setPaddingTopLeft: function setPaddingTopLeft (newVal, oldVal) {
      this.paddingTopLeft = newVal;
    },
    setPadding: function setPadding (newVal, oldVal) {
      this.padding = newVal;
    },
    setCrs: function setCrs (newVal, oldVal) {
      console.log('Changing CRS is not yet supported by Leaflet');
    },
    fitBounds: function fitBounds (bounds) {
      this.mapObject.fitBounds(bounds);
    },
    moveEndHandler: function moveEndHandler () {
      this.$emit('update:zoom', this.mapObject.getZoom());
      var center = this.mapObject.getCenter();
      this.$emit('update:center', center);
      var bounds = this.mapObject.getBounds();
      this.$emit('update:bounds', bounds);
    }
  }
};

function normalizeComponent(template, style, script, scopeId, isFunctionalTemplate, moduleIdentifier
/* server only */
, shadowMode, createInjector, createInjectorSSR, createInjectorShadow) {
  if (typeof shadowMode !== 'boolean') {
    createInjectorSSR = createInjector;
    createInjector = shadowMode;
    shadowMode = false;
  } // Vue.extend constructor export interop.


  var options = typeof script === 'function' ? script.options : script; // render functions

  if (template && template.render) {
    options.render = template.render;
    options.staticRenderFns = template.staticRenderFns;
    options._compiled = true; // functional template

    if (isFunctionalTemplate) {
      options.functional = true;
    }
  } // scopedId


  if (scopeId) {
    options._scopeId = scopeId;
  }

  var hook;

  if (moduleIdentifier) {
    // server build
    hook = function hook(context) {
      // 2.3 injection
      context = context || // cached call
      this.$vnode && this.$vnode.ssrContext || // stateful
      this.parent && this.parent.$vnode && this.parent.$vnode.ssrContext; // functional
      // 2.2 with runInNewContext: true

      if (!context && typeof __VUE_SSR_CONTEXT__ !== 'undefined') {
        context = __VUE_SSR_CONTEXT__;
      } // inject component styles


      if (style) {
        style.call(this, createInjectorSSR(context));
      } // register component module identifier for async chunk inference


      if (context && context._registeredComponents) {
        context._registeredComponents.add(moduleIdentifier);
      }
    }; // used by ssr in case component is cached and beforeCreate
    // never gets called


    options._ssrRegister = hook;
  } else if (style) {
    hook = shadowMode ? function () {
      style.call(this, createInjectorShadow(this.$root.$options.shadowRoot));
    } : function (context) {
      style.call(this, createInjector(context));
    };
  }

  if (hook) {
    if (options.functional) {
      // register for functional component in vue file
      var originalRender = options.render;

      options.render = function renderWithStyleInjection(h, context) {
        hook.call(context);
        return originalRender(h, context);
      };
    } else {
      // inject component registration as beforeCreate hook
      var existing = options.beforeCreate;
      options.beforeCreate = existing ? [].concat(existing, hook) : [hook];
    }
  }

  return script;
}

var normalizeComponent_1 = normalizeComponent;

var isOldIE = typeof navigator !== 'undefined' && /msie [6-9]\\b/.test(navigator.userAgent.toLowerCase());
function createInjector(context) {
  return function (id, style) {
    return addStyle(id, style);
  };
}
var HEAD = document.head || document.getElementsByTagName('head')[0];
var styles = {};

function addStyle(id, css) {
  var group = isOldIE ? css.media || 'default' : id;
  var style = styles[group] || (styles[group] = {
    ids: new Set(),
    styles: []
  });

  if (!style.ids.has(id)) {
    style.ids.add(id);
    var code = css.source;

    if (css.map) {
      // https://developer.chrome.com/devtools/docs/javascript-debugging
      // this makes source maps inside style tags work properly in Chrome
      code += '\n/*# sourceURL=' + css.map.sources[0] + ' */'; // http://stackoverflow.com/a/26603875

      code += '\n/*# sourceMappingURL=data:application/json;base64,' + btoa(unescape(encodeURIComponent(JSON.stringify(css.map)))) + ' */';
    }

    if (!style.element) {
      style.element = document.createElement('style');
      style.element.type = 'text/css';
      if (css.media) { style.element.setAttribute('media', css.media); }
      HEAD.appendChild(style.element);
    }

    if ('styleSheet' in style.element) {
      style.styles.push(code);
      style.element.styleSheet.cssText = style.styles.filter(Boolean).join('\n');
    } else {
      var index = style.ids.size - 1;
      var textNode = document.createTextNode(code);
      var nodes = style.element.childNodes;
      if (nodes[index]) { style.element.removeChild(nodes[index]); }
      if (nodes.length) { style.element.insertBefore(textNode, nodes[index]); }else { style.element.appendChild(textNode); }
    }
  }
}

var browser = createInjector;

/* script */
var __vue_script__ = script;

/* template */
var __vue_render__ = function () {var _vm=this;var _h=_vm.$createElement;var _c=_vm._self._c||_h;return _c('div',{staticClass:"vue2leaflet-map"},[(_vm.ready)?_vm._t("default"):_vm._e()],2)};
var __vue_staticRenderFns__ = [];

  /* style */
  var __vue_inject_styles__ = function (inject) {
    if (!inject) { return }
    inject("data-v-2935624e_0", { source: ".vue2leaflet-map{height:100%;width:100%}", map: undefined, media: undefined });

  };
  /* scoped */
  var __vue_scope_id__ = undefined;
  /* module identifier */
  var __vue_module_identifier__ = undefined;
  /* functional template */
  var __vue_is_functional_template__ = false;
  /* style inject SSR */
  

  
  var LMap = normalizeComponent_1(
    { render: __vue_render__, staticRenderFns: __vue_staticRenderFns__ },
    __vue_inject_styles__,
    __vue_script__,
    __vue_scope_id__,
    __vue_is_functional_template__,
    __vue_module_identifier__,
    browser,
    undefined
  );

export default LMap;
