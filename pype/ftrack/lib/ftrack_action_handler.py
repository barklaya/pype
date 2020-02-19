from .ftrack_base_handler import BaseHandler


class BaseAction(BaseHandler):
    '''Custom Action base class

    `label` a descriptive string identifing your action.

    `varaint` To group actions together, give them the same
    label and specify a unique variant per action.

    `identifier` a unique identifier for your action.

    `description` a verbose descriptive text for you action

     '''
    label = None
    variant = None
    identifier = None
    description = None
    icon = None
    type = 'Action'
    discover_roles = []

    def __init__(self, session, plugins_presets={}):
        '''Expects a ftrack_api.Session instance'''
        super().__init__(session, plugins_presets)

        if self.label is None:
            raise ValueError(
                'Action missing label.'
            )

        elif self.identifier is None:
            raise ValueError(
                'Action missing identifier.'
            )

        self.identifier = "{}.{}".format(
            self.identifier, session.event_hub.id
        )

    def register(self):
        '''
        Registers the action, subscribing the the discover and launch topics.
        - highest priority event will show last
        '''
        self.session.event_hub.subscribe(
            'topic=ftrack.action.discover and source.user.username={0}'.format(
                self.session.api_user
            ),
            self._discover,
            priority=self.priority
        )

        launch_subscription = (
            'topic=ftrack.action.launch'
            ' and data.actionIdentifier={0}'
            ' and source.user.username={1}'
        ).format(
            self.identifier,
            self.session.api_user
        )
        self.session.event_hub.subscribe(
            launch_subscription,
            self._launch
        )

    def _discover(self, event):
        args = self._translate_event(self.session, event)

        accepts = self.discover(self.session, *args)
        if not accepts:
            return None

        if self.discover_roles:
            user = self.get_user_from_event(event)
            if not user:
                return None

            lowercase_rolelist = [
                role_name.lower() for role_name in self.discover_roles
            ]
            available = False
            for role in user["user_security_roles"]:
                if role["security_role"]["name"].lower() in lowercase_rolelist:
                    available = True
                    break

            if not available:
                return None

        self.log.debug(
            'Discovering action with selection: {0}'.format(
                event['data'].get('selection', [])
            )
        )

        return {
            'items': [{
                'label': self.label,
                'variant': self.variant,
                'description': self.description,
                'actionIdentifier': self.identifier,
                'icon': self.icon,
            }]
        }

    def discover(self, session, entities, event):
        '''Return true if we can handle the selected entities.

        *session* is a `ftrack_api.Session` instance


        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event

        '''

        return False

    def _launch(self, event):
        args = self._translate_event(
            self.session, event
        )

        preactions_launched = self._handle_preactions(self.session, event)
        if preactions_launched is False:
            return

        interface = self._interface(
            self.session, *args
        )

        if interface:
            return interface

        response = self.launch(
            self.session, *args
        )

        return self._handle_result(
            self.session, response, *args
        )

    def _handle_result(self, session, result, entities, event):
        '''Validate the returned result from the action callback'''
        if isinstance(result, bool):
            if result is True:
                result = {
                    'success': result,
                    'message': (
                        '{0} launched successfully.'.format(self.label)
                    )
                }
            else:
                result = {
                    'success': result,
                    'message': (
                        '{0} launch failed.'.format(self.label)
                    )
                }

        elif isinstance(result, dict):
            if 'items' in result:
                items = result['items']
                if not isinstance(items, list):
                    raise ValueError('Invalid items format, must be list!')

            else:
                for key in ('success', 'message'):
                    if key in result:
                        continue

                    raise KeyError(
                        'Missing required key: {0}.'.format(key)
                    )

        else:
            self.log.error(
                'Invalid result type must be bool or dictionary!'
            )

        return result
