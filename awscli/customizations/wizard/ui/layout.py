# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.filters import has_focus, Condition
from prompt_toolkit.formatted_text import HTML, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import (
    focus_next, focus_previous
)
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    Window, HSplit, Dimension, ConditionalContainer, WindowAlign, VSplit,
    to_container, to_filter
)
from prompt_toolkit.widgets import (
    HorizontalLine, Box, Button, Label, Shadow, Frame
)

from awscli.autoprompt.widgets import BaseToolbarView, TitleLine
from awscli.customizations.wizard import core
from awscli.customizations.wizard.ui.section import (
    WizardSectionTab, WizardSectionBody
)
from awscli.customizations.wizard.ui.keybindings import (
    details_visible, prompt_has_details
)
from awscli.customizations.wizard.ui.utils import (
    move_to_previous_prompt, Spacer
)


class WizardLayoutFactory:
    def create_wizard_layout(self, definition):
        run_wizard_dialog = self._create_run_wizard_dialog(definition)
        layout = Layout(
            container=HSplit(
                [
                    self._create_title(definition),
                    self._create_sections(definition, run_wizard_dialog),
                    HorizontalLine()
                ],
            )
        )
        layout.run_wizard_dialog = run_wizard_dialog
        return layout

    def _create_title(self, definition):
        title = Label(f'{definition["title"]}', style='class:wizard.title')
        title.window.align = WindowAlign.CENTER
        return title

    def _create_sections(self, definition, run_wizard_dialog):
        section_tabs = []
        section_bodies = []
        for section_name, section_definition in definition['plan'].items():
            if section_name == core.DONE_SECTION_NAME:
                section_tabs.append(
                    self._create_done_section_tab(section_definition)
                )
                section_bodies.append(run_wizard_dialog)
            else:
                section_tabs.append(
                    self._create_section_tab(section_name, section_definition)
                )
                section_bodies.append(
                    self._create_section_body(section_name, section_definition)
                )
        section_tabs.append(Spacer())
        return VSplit(
            [
                HSplit(
                    section_tabs,
                    padding=1,
                    style='class:wizard.section.tab'
                ),
                HSplit([*section_bodies,
                        WizardDetailsPanel(),
                        DetailPanelToolbarView()])
            ]
        )

    def _create_section_tab(self, section_name, section_definition):
        return WizardSectionTab(section_name, section_definition)

    def _create_done_section_tab(self, done_definition):
        if not done_definition or 'shortname' not in done_definition:
            done_definition = {'shortname': 'Done'}
        return WizardSectionTab(core.DONE_SECTION_NAME, done_definition)

    def _create_section_body(self, section_name, section_definition):
        return WizardSectionBody(section_name, section_definition)

    def _create_run_wizard_dialog(self, wizard_defintion):
        done_section = wizard_defintion['plan'][core.DONE_SECTION_NAME]
        return RunWizardDialog.from_done_section_definition(done_section)


class WizardDetailsPanel:
    DIMENSIONS = {
        'details_window_height_max': 40,
        'details_window_height_pref': 30,
    }

    def __init__(self):
        self.container = self._get_container()

    def _get_title(self):
        return getattr(get_app(), 'details_title', '') or "Details panel"

    def _get_container(self):
        return ConditionalContainer(
            HSplit([
                TitleLine(self._get_title),
                Window(
                    content=BufferControl(
                        buffer=Buffer(name='details_buffer', read_only=True),
                    ),
                    height=Dimension(
                        max=self.DIMENSIONS['details_window_height_max'],
                        preferred=self.DIMENSIONS['details_window_height_pref']
                    ),
                    wrap_lines=True
                )
            ]),
            details_visible
        )

    def __pt_container__(self):
        return self.container


class DetailPanelToolbarView(BaseToolbarView):
    CONDITION = prompt_has_details

    def __init__(self):
        self.content = to_container(self.create_window(self.help_text))
        self.filter = to_filter(self.CONDITION)

    def create_window(self, help_text):
        text_control = FormattedTextControl(text=lambda: help_text)
        text_control.name = 'details_toolbar'
        return HSplit([
            HorizontalLine(),
            Window(
                content=text_control,
                wrap_lines=True,
                **self.DIMENSIONS
            )
        ])

    def help_text(self):
        app = get_app()
        title = getattr(app, 'details_title', 'Details panel')
        return to_formatted_text(HTML(
            f'{self.STYLE}[F2]</style> Switch to {title}{self.SPACING}'
            f'{self.STYLE}[F3]</style> Show/Hide {title}'
        ))


class RunWizardDialogButtonFactory:
    def create_button(self, button_name, text=None):
        button_kwargs = {}
        if text:
            button_kwargs['text'] = text
        return getattr(self, f'_create_{button_name}_button')(**button_kwargs)

    def _create_yes_button(self, text='Yes'):
        def yes_handler():
            get_app().exit(result=0)

        return self._create_dialog_button(text=text, handler=yes_handler)

    def _create_back_button(self, text='Back'):
        def back_handler():
            move_to_previous_prompt(get_app())

        return self._create_dialog_button(text=text, handler=back_handler)

    def _create_dialog_button(self, text, handler):
        button = Button(text=text, handler=handler)
        button.window.always_hide_cursor = to_filter(True)
        return button


class RunWizardDialog:
    _DEFAULT_BUTTONS = ['yes', 'back']

    def __init__(self, title='Run wizard?', buttons=None):
        self._title = title
        if buttons is None:
            buttons = self._create_default_buttons()
        self._buttons = buttons
        self.container = self._get_container()

    @classmethod
    def from_done_section_definition(cls, done_section_definition):
        cls_kwargs = {}
        if done_section_definition:
            if 'description' in done_section_definition:
                cls_kwargs['title'] = done_section_definition['description']
            if 'options' in done_section_definition:
                buttons = []
                button_factory = RunWizardDialogButtonFactory()
                for option in done_section_definition['options']:
                    create_button_kwargs = {'button_name': option}
                    if isinstance(option, dict):
                        create_button_kwargs['button_name'] = option['name']
                        create_button_kwargs['text'] = option.get(
                            'description'
                        )
                    buttons.append(
                        button_factory.create_button(**create_button_kwargs)
                    )
                cls_kwargs['buttons'] = buttons
        return cls(**cls_kwargs)

    def _get_container(self):
        dialog = Box(
            body=self._create_dialog_frame(),
            style='class:wizard.dialog',
            padding_top=5,
        )
        return ConditionalContainer(
            dialog,
            Condition(self._is_visible),
        )

    def _is_visible(self):
        return get_app().traverser.has_no_remaining_prompts()

    def _create_default_buttons(self):
        buttons = []
        button_factory = RunWizardDialogButtonFactory()
        for button_name in self._DEFAULT_BUTTONS:
            buttons.append(button_factory.create_button(button_name))
        return buttons

    def _create_dialog_frame(self):
        frame_body = Box(
            body=self._create_buttons_container(),
            height=Dimension(min=1, max=3, preferred=3)
        )
        return Shadow(
            body=Frame(
                title=self._title,
                body=frame_body,
                style='class:wizard.dialog.body',
            )
        )

    def _create_buttons_container(self):
        buttons_kb = self._create_buttons_key_bindings(self._buttons)
        return VSplit(self._buttons, padding=1, key_bindings=buttons_kb)

    def _create_buttons_key_bindings(self, buttons):
        kb = KeyBindings()
        first_selected = has_focus(buttons[0])
        last_selected = has_focus(buttons[-1])

        kb.add(Keys.Left, filter=~first_selected)(focus_previous)
        kb.add(Keys.Right, filter=~last_selected)(focus_next)
        kb.add(Keys.Tab)(focus_next)
        kb.add(Keys.BackTab)(focus_previous)
        return kb

    def __pt_container__(self):
        return self.container